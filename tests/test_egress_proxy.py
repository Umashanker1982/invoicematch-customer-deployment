"""Unit tests for the egress proxy's allow-list logic (standard library only)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("proxy", ROOT / "customer-env" / "egress-proxy" / "proxy.py")
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class AllowListTests(unittest.TestCase):
    def test_shipped_allowlist_has_only_the_ai_gateway(self):
        self.assertEqual(proxy.load_allowlist(), {("api.sharedllm.com", 443)})

    def test_comments_and_default_port(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# comment\nExample.org   # trailing\napi.test:8443\n\n")
        self.assertEqual(proxy.load_allowlist(Path(f.name)), {("example.org", 443), ("api.test", 8443)})

    def test_parse_connect(self):
        self.assertEqual(proxy.parse_target("CONNECT api.sharedllm.com:443 HTTP/1.1"), ("CONNECT", "api.sharedllm.com", 443))
        self.assertIsNone(proxy.parse_target("CONNECT nohostport HTTP/1.1"))
        self.assertIsNone(proxy.parse_target("garbage"))

    def test_only_connect_to_allowed_host_and_port(self):
        allowed = {("api.sharedllm.com", 443)}
        self.assertTrue(proxy.is_allowed("CONNECT", "api.sharedllm.com", 443, allowed))
        self.assertFalse(proxy.is_allowed("CONNECT", "api.sharedllm.com", 80, allowed))
        self.assertFalse(proxy.is_allowed("CONNECT", "example.com", 443, allowed))
        self.assertFalse(proxy.is_allowed("GET", "http://api.sharedllm.com/", 0, allowed))


if __name__ == "__main__":
    unittest.main()
