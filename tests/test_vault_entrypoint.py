"""Unit tests for the Vault start-up wrapper, against a small fake Vault server."""
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk-sharedllm-unit-test-WXYZ"


class FakeVault(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/v1/auth/approle/login":
            if body == {"role_id": "rid", "secret_id": "sid"}:
                return self._send(200, {"auth": {"client_token": "tok", "policies": ["invoicematch-app"], "lease_duration": 900}})
            return self._send(400, {"errors": ["invalid role or secret id"]})
        self._send(204, {})

    def do_GET(self):
        if self.path == "/v1/secret/data/invoicematch/llm" and self.headers.get("X-Vault-Token") == "tok":
            return self._send(200, {"data": {"data": {"SHAREDLLM_KEY": KEY}}})
        self._send(403, {"errors": ["permission denied"]})


class EntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeVault)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def load(self, secret_id="sid", retries="2"):
        creds = Path(tempfile.mkdtemp())
        (creds / "role_id").write_text("rid\n")
        (creds / "secret_id").write_text(secret_id + "\n")
        env = {"VAULT_ADDR": f"http://127.0.0.1:{self.server.server_port}", "VAULT_CREDS_DIR": str(creds),
               "VAULT_RETRIES": retries, "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9"}
        with mock.patch.dict(os.environ, env):
            spec = importlib.util.spec_from_file_location("ep", ROOT / "customer-env" / "app" / "vault_entrypoint.py")
            ep = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ep)
        return ep, env

    def test_loads_key_from_vault_and_starts_server_without_printing_it(self):
        ep, env = self.load()
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch.object(ep.os, "execvp") as execvp, redirect_stdout(out):
            ep.main()
            self.assertEqual(os.environ["SHAREDLLM_KEY"], KEY)
        execvp.assert_called_once()
        self.assertEqual(execvp.call_args[0][0], "uvicorn")
        self.assertNotIn(KEY, out.getvalue())          # never printed in full
        self.assertIn("...WXYZ", out.getvalue())        # only the last 4 characters

    def test_wrong_credentials_stop_the_app(self):
        ep, env = self.load(secret_id="wrong")
        with mock.patch.dict(os.environ, env), mock.patch.object(ep.time, "sleep"), \
                mock.patch.object(ep.os, "execvp") as execvp, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                ep.main()
        execvp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
