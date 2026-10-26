import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

server = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(server))
spec = importlib.util.spec_from_file_location("prodigi_shortlist", server / "scripts/prodigi_shortlist.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ShortlistTests(unittest.IsolatedAsyncioTestCase):
    def product(self):
        return {"sku": "SKU", "printAreas": {"front": {"required": True},
                "back": {"required": True}, "optional": {"required": False}},
                "variants": [
                    {"shipsTo": ["GB"], "attributes": {"color": "black"}},
                    {"shipsTo": ["US"], "attributes": {"color": "white"}},
                    {"shipsTo": ["US"], "attributes": {"color": "black"}},
                ]}

    def test_us_variant_and_all_required_areas(self):
        item = m.quote_item(self.product())
        self.assertEqual(item["attributes"], {"color": "black"})
        self.assertEqual(item["assets"], [{"printArea": "front"}, {"printArea": "back"}])
        self.assertEqual(item["copies"], 1)

    async def test_unavailable_products_never_quoted(self):
        product = self.product()
        product["variants"] = [{"shipsTo": ["GB"]}]
        client = AsyncMock()
        client.product_details.return_value = {"product": product}
        record = await m.inspect(client, "Name", "SKU")
        self.assertIn("error", record)
        client.quote_us.assert_not_awaited()

    async def test_one_item_quote_retains_tax_warning_and_production_country(self):
        client = AsyncMock()
        client.product_details.return_value = {"product": self.product()}
        client.quote_us.return_value = {"outcome": "CreatedWithIssues",
            "issues": [{"errorCode": "TaxWarning"}], "quotes": [{
                "shipmentMethod": "Budget", "costSummary": {"totalCost": {"amount": "10", "currency": "USD"}},
                "shipments": [{"fulfillmentLocation": {"countryCode": "US"}}]}]}
        record = await m.inspect(client, "Name", "SKU")
        self.assertEqual(len(client.quote_us.call_args.args[0]), 1)
        self.assertEqual(record["issues"], [{"errorCode": "TaxWarning"}])
        self.assertEqual(record["quotes"][0]["fulfillment_countries"], ["US"])
