import importlib.util
import json
import unittest
from pathlib import Path

import httpx

spec = importlib.util.spec_from_file_location(
    "prodigi_under_test", Path(__file__).resolve().parents[1] / "services/prodigi.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProdigiTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_product_lookup_and_order_guard(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(str(request.url),
                             "https://api.prodigi.com/v4.0/products/GLOBAL-CAN-10X10")
            self.assertEqual(request.headers["X-API-Key"], "offline-key")
            return httpx.Response(200, json={"outcome": "Ok", "product": {
                "sku": "GLOBAL-CAN-10X10", "variants": []}})
        async with module.Client("offline-key", transport=httpx.MockTransport(handler)) as client:
            await client.product_details("GLOBAL-CAN-10X10")
            for method, path in [("POST", "/orders"), ("GET", "/orders"),
                                 ("POST", "/orders/123/cancel"),
                                 ("DELETE", "/products/123"),
                                 ("GET", "https://example.com"),
                                 ("POST", "/Quotes"), ("GET", "/products/../orders")]:
                with self.assertRaises(module.ProdigiError):
                    await client._request(method, path)
            with self.assertRaises(module.ProdigiError):
                await client.create_order({})
            for sku in ("../orders", "SKU?x=y", "SKU/extra", "", "SKU\n"):
                with self.assertRaises(module.ProdigiError):
                    await client.product_details(sku)
        self.assertEqual(len(calls), 1)

    async def test_us_quote_payload_and_issues_preserved(self):
        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://api.prodigi.com/v4.0/quotes")
            body = json.loads(request.content)
            self.assertEqual(body, {
                "destinationCountryCode": "US", "currencyCode": "USD",
                "items": [{"sku": "GLOBAL-CAN-10X10", "copies": 1,
                           "attributes": {"wrap": "ImageWrap"},
                           "assets": [{"printArea": "default"}]}],
            })
            return httpx.Response(200, json={"outcome": "CreatedWithIssues",
                "quotes": [{"costSummary": {"items": {"amount": "10", "currency": "USD"}}}],
                "issues": [{"errorCode": "destinationCountryCode.UsSalesTaxWarning"}]})
        async with module.Client("offline-key", transport=httpx.MockTransport(handler)) as client:
            result = await client.quote_us([{
                "sku": "GLOBAL-CAN-10X10", "attributes": {"wrap": "ImageWrap"},
                "assets": [{"printArea": "default"}],
            }])
        self.assertEqual(result["issues"][0]["errorCode"],
                         "destinationCountryCode.UsSalesTaxWarning")

    async def test_quote_rejects_order_fields_and_bad_quantities_before_network(self):
        calls = []
        async with module.Client("offline-key", transport=httpx.MockTransport(
            lambda r: calls.append(r)
        )) as client:
            item = {"sku": "GLOBAL-FAP-10X10", "assets": [{"printArea": "default"}]}
            for items in ([], [item] * 21, [{**item, "copies": True}],
                          [{**item, "copies": 0}], [{**item, "recipient": {}}],
                          [{**item, "assets": [{"printArea": "default", "url": "https://example.com"}]}]):
                with self.assertRaises(module.ProdigiError):
                    await client.quote_us(items)
        self.assertEqual(calls, [])

    async def test_safe_upstream_failures(self):
        cases = [(401, {"error": "offline-key"}), (429, {}),
                 (302, {}), (200, []), (200, {"outcome": "ValidationFailed"}),
                 (200, {"outcome": "Ok", "product": {"sku": "OTHER", "variants": []}})]
        for status, body in cases:
            with self.subTest(status=status, body=body):
                async with module.Client("offline-key", transport=httpx.MockTransport(
                    lambda r: httpx.Response(status, json=body)
                )) as client:
                    with self.assertRaises(module.ProdigiError) as error:
                        await client.product_details("SKU")
                    self.assertNotIn("offline-key", str(error.exception))
        for body in ({"outcome": "Created", "quotes": []},
                     {"outcome": "Created", "quotes": [None]}):
            async with module.Client("offline-key", transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=body)
            )) as client:
                with self.assertRaises(module.ProdigiError):
                    await client.quote_us([{"sku": "SKU", "assets": [{"printArea": "default"}]}])

    async def test_malformed_json_and_timeout_are_safe(self):
        def timeout(request):
            raise httpx.ReadTimeout("offline-key")
        for handler in (timeout, lambda r: httpx.Response(200, text="offline-key")):
            async with module.Client("offline-key", transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(module.ProdigiError) as error:
                    await client.product_details("SKU")
                self.assertNotIn("offline-key", str(error.exception))

    async def test_missing_key(self):
        for key in (None, "", " "):
            with self.assertRaises(module.ProdigiError):
                module.Client(key)


if __name__ == "__main__":
    unittest.main()
