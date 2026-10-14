"""Offline diagnostics tests: no production credentials or network calls."""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_integrations as checks


class IntegrationCheckTests(unittest.TestCase):
    def test_errors_do_not_disclose_exception_content(self):
        def fail():
            raise RuntimeError("credential-that-must-not-be-printed")
        data = checks.safe_check(fail)
        self.assertEqual(data["status"], "FAIL")
        self.assertNotIn("credential-that-must-not-be-printed", json.dumps(data))

    def test_smtp_refuses_authentication_without_tls(self):
        with patch.dict(os.environ, {"SMTP_HOST": "example.com", "SMTP_USER": "u", "SMTP_PASSWORD": "p", "MAIL_FROM": "u@example.com", "SMTP_SSL": "0", "SMTP_STARTTLS": "0"}, clear=True), patch.object(checks.smtplib, "SMTP") as connect:
            self.assertEqual(checks.smtp()["status"], "FAIL")
            connect.assert_not_called()

    def test_dataset_read_denial_is_not_claimed_as_capi_failure(self):
        def respond(request):
            self.assertEqual(request.method, "GET")
            self.assertNotIn("events", request.url.path)
            if request.url.path.endswith("debug_token"):
                return httpx.Response(200, json={"data": {"is_valid": True}})
            return httpx.Response(403)
        with patch.dict(os.environ, {"META_PIXEL_ID": "123", "META_CAPI_TOKEN": "test"}, clear=True), httpx.Client(transport=httpx.MockTransport(respond)) as client:
            self.assertEqual(checks.meta(client)["status"], "LIMITED")

    def test_main_runs_all_checks_and_preserves_failure_exit(self):
        with patch.object(checks, "load_dotenv"), patch.object(checks, "paypal", return_value=checks.result("FAIL", "failed")), patch.object(checks, "smtp", return_value=checks.result("PASS", "ok")), patch.object(checks, "meta", return_value=checks.result("LIMITED", "unknown")), patch.object(checks, "uptimerobot", return_value=checks.result("PASS", "ok")), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(checks.main(), 1)
        self.assertEqual(len(json.loads(output.getvalue())["checks"]), 4)


if __name__ == "__main__":
    unittest.main()
