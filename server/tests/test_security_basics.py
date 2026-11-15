"""CORS and admin-key basics. Nothing is started: preflights are answered by the middleware."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from fastapi.testclient import TestClient


class CorsTests(unittest.TestCase):
    def preflight(self, origin):
        return TestClient(main.app).options("/api/newsletter/subscribe", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST"})

    def test_site_origin_is_allowed_with_credentials(self):
        r = self.preflight(main.PUBLIC_BASE)
        self.assertEqual(r.headers.get("access-control-allow-origin"), main.PUBLIC_BASE)
        self.assertEqual(r.headers.get("access-control-allow-credentials"), "true")

    def test_null_localhost_and_foreign_origins_are_refused_by_default(self):
        for origin in ("null", "http://localhost:8765", "http://127.0.0.1:8765", "https://evil.example"):
            self.assertIsNone(self.preflight(origin).headers.get("access-control-allow-origin"), origin)
        self.assertNotIn("null", main._CORS_ORIGINS)


class AdminKeyTests(unittest.TestCase):
    def test_only_the_exact_key_passes_and_an_unset_key_never_does(self):
        with patch.dict(os.environ, {"SECRET_KEY": "s3cret-value"}):
            self.assertTrue(main._admin_ok("s3cret-value"))
            for bad in ("", "s3cret-valu", "s3cret-value ", "S3CRET-VALUE", "ñ"):
                self.assertFalse(main._admin_ok(bad), bad)
        with patch.dict(os.environ, {"SECRET_KEY": ""}):
            self.assertFalse(main._admin_ok(""))


if __name__ == "__main__":
    unittest.main()
