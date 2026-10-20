import asyncio
import importlib.util
import unittest
from pathlib import Path
from urllib.parse import parse_qs
import httpx

path = Path(__file__).resolve().parents[1] / "services/qikink_live.py"
spec = importlib.util.spec_from_file_location("qikink_live_under_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class LiveClientTests(unittest.TestCase):
    def test_authentication_and_order_block(self):
        async def scenario():
            calls = []
            def handler(request):
                calls.append(request)
                self.assertEqual(request.method, "POST")
                self.assertEqual(
                    str(request.url), "https://api.qikink.com/api/token"
                )
                self.assertEqual(
                    parse_qs(request.content.decode()),
                    {"ClientId": ["123"], "client_secret": ["test-secret"]},
                )
                return httpx.Response(200, json={
                    "ClientId": 123,
                    "Accesstoken": "test-token",
                    "expires_in": 3600,
                })
            async with module.LiveClient(
                "123", "test-secret", transport=httpx.MockTransport(handler)
            ) as client:
                report = await client.authenticate()
                self.assertTrue(report["authenticated"])
                self.assertFalse(report["order_submission_enabled"])
                self.assertNotIn("test-token", str(report))
                self.assertNotIn("test-secret", str(report))
                for method in (
                    client.create_plain_order, client.create_printed_order
                ):
                    with self.assertRaises(module.QikinkLiveError):
                        await method({})
                self.assertEqual(len(calls), 1)
        asyncio.run(scenario())

    def test_rejected_and_invalid_authentication(self):
        cases = [
            (401, {"error": "test-secret"}),
            (200, {"ClientId": 123, "Accesstoken": "", "expires_in": 3600}),
            (200, {"ClientId": 999, "Accesstoken": "test-token", "expires_in": 3600}),
            (200, {"ClientId": 123, "Accesstoken": "test-token", "expires_in": 0}),
            (200, {"ClientId": 123, "Accesstoken": "test-token", "expires_in": True}),
            (200, []),
        ]
        for status, body in cases:
            with self.subTest(status=status, body=body):
                async def scenario():
                    def handler(request):
                        return httpx.Response(status, json=body)
                    async with module.LiveClient(
                        "123", "test-secret",
                        transport=httpx.MockTransport(handler),
                    ) as client:
                        with self.assertRaises(module.QikinkLiveError) as error:
                            await client.authenticate()
                        self.assertNotIn("test-secret", str(error.exception))
                        self.assertNotIn("test-token", str(error.exception))
                asyncio.run(scenario())

    def test_missing_credentials(self):
        for identifier, secret in [("", "secret"), ("123", ""), (" ", " ")]:
            with self.assertRaises(module.QikinkLiveError):
                module.LiveClient(identifier, secret)

if __name__ == "__main__":
    unittest.main()
