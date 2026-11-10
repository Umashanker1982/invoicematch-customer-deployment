"""Start InvoiceMatch with its secret fetched from HashiCorp Vault.

1. Log in to Vault with the application's AppRole (role_id + secret_id, mounted
   read-only by the platform; never baked into the image or written to env files).
2. Read the AI gateway key from the one path the app's policy allows.
3. Put the key in this process's environment only, then replace this process
   with the web server (exec), so the key lives only in the running app's memory.

The key is never printed: only its last 4 characters appear in the log.
Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://vault:8200").rstrip("/")
SECRET_PATH = os.environ.get("VAULT_SECRET_PATH", "secret/data/invoicematch/llm")
CREDS_DIR = Path(os.environ.get("VAULT_CREDS_DIR", "/vault/creds"))
RETRIES = int(os.environ.get("VAULT_RETRIES", "30"))

# Vault is inside the private network: never send these requests through the egress proxy.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


def vault(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    req = urllib.request.Request(f"{VAULT_ADDR}/v1/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"X-Vault-Token": token} if token else {})})
    with _opener.open(req, timeout=5) as resp:
        return json.loads(resp.read() or b"{}")


def fetch_secret() -> dict[str, str]:
    role_id = (CREDS_DIR / "role_id").read_text().strip()
    secret_id = (CREDS_DIR / "secret_id").read_text().strip()
    login = vault("POST", "auth/approle/login", {"role_id": role_id, "secret_id": secret_id})
    token = login["auth"]["client_token"]
    log("vault_login_ok", policies=login["auth"].get("policies"), ttl_s=login["auth"].get("lease_duration"))
    data = vault("GET", SECRET_PATH, token=token)["data"]["data"]
    # Give the token back right away: the app needs the secret once, at start-up.
    try:
        vault("POST", "auth/token/revoke-self", {}, token=token)
    except urllib.error.URLError:
        pass
    return data


def main() -> None:
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            secrets = fetch_secret()
            break
        except (OSError, KeyError, ValueError, urllib.error.URLError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            log("vault_not_ready", attempt=attempt, error=last_error[:120])
            time.sleep(2)
    else:
        log("vault_failed", error=last_error)
        sys.exit(1)

    for name, value in secrets.items():
        os.environ[name] = value
    key = os.environ.get("SHAREDLLM_KEY", "")
    log("secret_loaded", source=f"vault:{SECRET_PATH}", names=sorted(secrets), key_hint=f"...{key[-4:]}" if key else None)

    port = os.environ.get("PORT", "8000")
    os.execvp("uvicorn", ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", port,
                          "--proxy-headers", "--forwarded-allow-ips=*"])


if __name__ == "__main__":
    main()
