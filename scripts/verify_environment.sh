#!/usr/bin/env bash
# Verify that InvoiceMatch runs inside the simulated customer environment and that
# every security control actually holds. Each check prints PASS or FAIL; any FAIL
# makes the script (and the CI run) fail.
#
# Usage (from the repository root, with the environment already started):
#   VAULT_ROOT_TOKEN=... bash scripts/verify_environment.sh
set -uo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f customer-env/docker-compose.yml)
INGRESS="http://127.0.0.1:8080"
FAILED=0

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILED=1; }
check()     { local name="$1"; shift; if "$@" >/dev/null 2>&1; then pass "$name"; else fail "$name"; fi; }
check_not() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then fail "$name"; else pass "$name"; fi; }

app_id()  { "${COMPOSE[@]}" ps -q app; }
in_app()  { "${COMPOSE[@]}" exec -T app "$@"; }
logs_of() { "${COMPOSE[@]}" logs --no-color "$1"; }

# --- helpers used by the checks ---------------------------------------------
PAYLOADS=$(mktemp -d)
make_payload() {
  python3 -c 'import json,sys; json.dump({"text": open(sys.argv[1]).read(), "mode": sys.argv[2]}, open(sys.argv[3], "w"))' "$1" "$2" "$3"
}
make_payload app-src/data/invoices/invoice_05.txt rules  "$PAYLOADS/inv05.json"
make_payload app-src/data/invoices/invoice_11.txt rules  "$PAYLOADS/inv11.json"
make_payload app-src/data/invoices/invoice_05.txt claude "$PAYLOADS/inv05_claude.json"

http_has()  { curl -fsS --max-time 10 "$INGRESS$1" | grep -q "$2"; }
post_has()  { curl -fsS --max-time 60 -X POST "$INGRESS/api/process" -H 'Content-Type: application/json' \
                -H "X-Visitor: $2" --data-binary "@$1" | grep -q "$3"; }
logs_have() { logs_of "$1" | grep -q "$2"; }

no_direct_internet() {
  in_app python -c "import urllib.request as u; u.build_opener(u.ProxyHandler({})).open('https://example.com', timeout=5)"
}
proxy_refuses_example() {
  in_app python -c "
import http.client, sys
c = http.client.HTTPConnection('egress-proxy', 3128, timeout=10); c.set_tunnel('example.com', 443)
try:
    c.request('GET', '/'); sys.exit(1)
except OSError as e:
    sys.exit(0 if '403' in str(e) else 1)"
}
proxy_allows_gateway() {
  in_app python -c "
import http.client, ssl
c = http.client.HTTPSConnection('egress-proxy', 3128, timeout=15, context=ssl.create_default_context())
c.set_tunnel('api.sharedllm.com', 443); c.request('GET', '/'); c.getresponse()"
}
key_in_container_config() { docker inspect "$(app_id)" | grep -q SHAREDLLM_KEY; }
audit_has_app_read()      { "${COMPOSE[@]}" exec -T vault grep -q 'secret/data/invoicematch/llm' /vault/logs/audit.log; }
key_in_repository()       { git grep -nE 'sk-sharedllm-[A-Za-z0-9-]{20,}' | grep -v placeholder; }

# Run a Vault CLI command as the APPLICATION's identity (AppRole), not as an admin.
vault_as_app() {
  "${COMPOSE[@]}" exec -T -e VAULT_TOKEN="$VAULT_ROOT_TOKEN" vault sh -c '
    RID=$(vault read -field=role_id auth/approle/role/invoicematch-app/role-id)
    SID=$(vault write -f -field=secret_id auth/approle/role/invoicematch-app/secret-id)
    export VAULT_TOKEN=$(vault write -field=token auth/approle/login role_id="$RID" secret_id="$SID")
    '"$1"
}
app_reads_own_secret()   { vault_as_app 'vault read -format=json secret/data/invoicematch/llm | grep -q SHAREDLLM_KEY'; }
app_reads_other_secret() { vault_as_app 'vault read secret/data/finance/erp'; }
app_writes_own_secret()  { vault_as_app 'echo "{\"data\":{\"SHAREDLLM_KEY\":\"changed\"}}" | vault write secret/data/invoicematch/llm -'; }
app_lists_secrets()      { vault_as_app 'vault list secret/metadata/'; }

app_is_uid_10001()  { [ "$(in_app id -u | tr -d '\r')" = "10001" ]; }
app_can_write_fs()  { in_app sh -c 'touch /app/should-fail'; }
app_is_hardened()   {
  docker inspect "$(app_id)" | grep -q 'no-new-privileges:true' &&
  docker inspect --format '{{.HostConfig.CapDrop}}' "$(app_id)" | grep -q ALL
}

# --- the checks ---------------------------------------------------------------
echo "== 1. The application runs in the customer environment"
check "App is healthy behind the internal ingress (/healthz)"     http_has /healthz '"ok"'
check "App serves the customer configuration (Silverbrook)"       http_has /api/config Silverbrook
check "A clean invoice is auto-approved end to end (invoice 05)"  post_has "$PAYLOADS/inv05.json" 0123456789abcdef '"route": *"auto_approve"'
check "A price mismatch is sent to people (invoice 11)"           post_has "$PAYLOADS/inv11.json" 0123456789abcdef '"route": *"review"'

echo "== 2. Network boundaries"
check_not "App container has no direct internet access"                      no_direct_internet
check     "Egress proxy refuses hosts not on the allow-list (example.com)"   proxy_refuses_example
check     "Egress proxy allows the approved AI gateway (api.sharedllm.com)"  proxy_allows_gateway
check     "Egress proxy logged the refused attempt"                          logs_have egress-proxy '"egress_denied".*example.com'
check_not "Vault is not reachable from outside the private network"          curl -fsS --max-time 3 http://127.0.0.1:8200/v1/sys/health
check_not "App port 8000 is not reachable from outside (only the ingress)"   curl -fsS --max-time 3 http://127.0.0.1:8000/healthz

echo "== 3. Secrets management (HashiCorp Vault)"
check     "App received the AI gateway key from Vault (AI is enabled)"       http_has /api/config '"ai_available": *true'
check     "App log shows the key was loaded from Vault (masked)"             logs_have app '"secret_loaded".*vault:secret/data/invoicematch/llm'
check_not "The key is not in the container's configuration (docker inspect)" key_in_container_config
check_not "No real key is stored anywhere in this repository"                key_in_repository
check     "Vault audit log recorded the app's secret read"                   audit_has_app_read

echo "== 4. Least privilege (Vault policy for the app's identity)"
check     "App identity CAN read its own secret"                             app_reads_own_secret
check_not "App identity CANNOT read another team's secret"                   app_reads_other_secret
check_not "App identity CANNOT change its own secret"                        app_writes_own_secret
check_not "App identity CANNOT list secrets"                                 app_lists_secrets

echo "== 5. Container hardening"
check     "App runs as a non-root user (uid 10001)"                          app_is_uid_10001
check_not "App file system is read-only"                                     app_can_write_fs
check     "App runs with all Linux capabilities dropped and no-new-privileges" app_is_hardened

if [ -n "${REAL_KEY_PROVIDED:-}" ]; then
  echo "== 6. Real AI call through the egress proxy (a real key was provided)"
  check "Claude read the invoice through the gateway via the egress proxy" \
        post_has "$PAYLOADS/inv05_claude.json" fedcba9876543210 '"read_by": *"claude"'
else
  echo "== 6. Real AI call: skipped (no real key provided; Vault holds a placeholder)"
fi

echo
if [ "$FAILED" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "SOME CHECKS FAILED"; fi
exit "$FAILED"
