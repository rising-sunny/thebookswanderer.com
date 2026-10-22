"""Offline staging: missing costs stay unknown; no store writes or remote calls."""
from datetime import date
from decimal import Decimal
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from services.qikink_catalog import DraftCatalog, catalog_report, load_catalog
from services.qikink import SandboxClient
import qikink_sandbox as cli

TODAY = date(2026, 10, 19)
PRICING = {"MARGIN_PCT": "0.40", "PAYPAL_PCT": "0.0349", "PAYPAL_FIXED": "0.49",
           "OPS_FIXED": "0.35", "MIN_PRICE": "6.99"}


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "store.db"
        self.data = load_catalog().model_dump(mode="json")

    def quote(self, **changes):
        return dict(sku="MVnHs-Wh-S", design=self.data["variants"][0]["design"], quantity=1, country="IN", postal_code="641001",
                    method="Test quote method", eta_min_days=5, eta_max_days=10,
                    currency="INR", product="200", printing="100", packaging="10",
                    tax="30", shipping="60", other="0", source="Operator supplied test fixture, NOT a real quote",
                    confirmed_on="2026-10-18", valid_until="2026-10-20") | changes

    def fx(self, **changes):
        return dict(currency_pair="INR_USD", usd_per_inr="0.012", source="Test fixture, NOT a live FX rate",
                    confirmed_on="2026-10-18", valid_until="2026-10-20") | changes

    def report(self):
        return catalog_report(DraftCatalog.model_validate(self.data), self.db, today=TODAY, pricing=PRICING)

    def test_draft_uses_confirmed_design_order_without_inventing_costs_or_mapping(self):
        result = self.report()
        self.assertFalse(result["public_sales_enabled"])
        row = result["variants"][0]
        self.assertEqual(row["sandbox_order_id"], "24620736")
        self.assertIsNone(row["store_product_id"])
        self.assertIn("sales_destinations_not_selected", row["blockers"])
        self.assertIn("real_product_mockup_not_supplied", row["blockers"])
        self.assertFalse(self.db.exists())

    def test_requested_destinations_without_quotes_are_unknown_not_free(self):
        self.data["requested_countries"] = ["US", "CL", "IN"]
        rows = self.report()["variants"][0]["destinations"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["state"] == "quote_required" and row["retail_estimate_usd"] is None for row in rows))

    def test_complete_quote_and_fx_calculate_destination_specific_all_in_estimate(self):
        self.data["requested_countries"] = ["IN"]
        self.data["variants"][0]["cost_quotes"] = [self.quote()]
        self.data["fx"] = self.fx()
        result = self.report()
        row = result["variants"][0]["destinations"][0]
        self.assertEqual(Decimal(row["all_in_cost_inr"]), Decimal("400"))
        self.assertEqual(Decimal(row["all_in_cost_usd"]), Decimal("4.8"))
        self.assertEqual(row["retail_estimate_usd"], "9.99")
        self.assertEqual(row["postal_code"], "641001")
        self.assertEqual(row["quantity"], 1)
        self.assertEqual(row["state"], "worksheet_only")
        self.assertFalse(result["public_sales_enabled"])

    def test_expired_or_future_quote_does_not_price_or_enable_destination(self):
        self.data["requested_countries"] = ["IN"]
        for dates in ({"confirmed_on": "2026-10-01", "valid_until": "2026-10-18"},
                      {"confirmed_on": "2026-10-20", "valid_until": "2026-10-21"}):
            self.data["variants"][0]["cost_quotes"] = [self.quote(**dates)]
            self.assertEqual(self.report()["variants"][0]["destinations"][0]["state"], "quote_required")

    def test_fx_is_required_current_and_correct_direction(self):
        self.data["requested_countries"] = ["IN"]
        self.data["variants"][0]["cost_quotes"] = [self.quote()]
        for fx in (None, self.fx(confirmed_on="2026-10-01", valid_until="2026-10-18")):
            self.data["fx"] = fx
            self.assertEqual(self.report()["variants"][0]["destinations"][0]["state"], "fx_required")
        self.data["fx"] = self.fx(currency_pair="USD_INR")
        with self.assertRaises(ValidationError):
            self.report()

    def test_incomplete_nonfinite_wrong_sku_or_wrong_quantity_quotes_are_rejected(self):
        for change in ({"sku": "OTHER-SKU"}, {"design": self.data["variants"][0]["design"] | {"width_inches": 3}}, {"quantity": 2}, {"shipping": "NaN"},
                       {"product": "-1"}, {"eta_min_days": 15, "eta_max_days": 3}):
            self.data["variants"][0]["cost_quotes"] = [self.quote(**change)]
            with self.assertRaises(ValidationError):
                self.report()
        incomplete = self.quote()
        del incomplete["tax"]
        self.data["variants"][0]["cost_quotes"] = [incomplete]
        with self.assertRaises(ValidationError):
            self.report()

    def test_wrong_country_quote_does_not_enable_other_countries(self):
        self.data["requested_countries"] = ["US"]
        self.data["variants"][0]["cost_quotes"] = [self.quote()]
        self.data["fx"] = self.fx()
        self.assertEqual(self.report()["variants"][0]["destinations"][0]["state"], "quote_required")

    def make_store(self):
        with sqlite3.connect(self.db) as db:
            db.executescript('''CREATE TABLE products (id INTEGER, active INTEGER);
                CREATE TABLE product_variants (id INTEGER, product_id INTEGER, active INTEGER);
                INSERT INTO products VALUES (1,0), (2,1);
                INSERT INTO product_variants VALUES (10,1,0), (20,2,1);''')
        self.data["variants"][0].update(store_product_id=1, store_variant_id=10)

    def test_mapping_is_read_only_and_validates_variant_parent(self):
        self.make_store()
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertNotIn("store_mapping_unverified", self.report()["variants"][0]["blockers"])
        self.data["variants"][0]["store_variant_id"] = 20
        self.assertIn("store_variant_does_not_belong_to_product", self.report()["variants"][0]["blockers"])
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

    def test_active_product_or_variant_is_blocked_for_staging(self):
        self.make_store()
        self.data["variants"][0].update(store_product_id=2, store_variant_id=20)
        self.assertIn("linked_store_product_or_variant_is_active", self.report()["variants"][0]["blockers"])

    def test_missing_database_is_not_created_by_lookup(self):
        self.data["variants"][0].update(store_product_id=1, store_variant_id=10)
        self.assertIn("store_mapping_unverified", self.report()["variants"][0]["blockers"])
        self.assertFalse(self.db.exists())

    def test_invalid_pricing_assumptions_never_produce_estimate(self):
        self.data["requested_countries"] = ["IN"]
        self.data["variants"][0]["cost_quotes"] = [self.quote()]
        self.data["fx"] = self.fx()
        result = catalog_report(DraftCatalog.model_validate(self.data), self.db, today=TODAY,
                                pricing=PRICING | {"MARGIN_PCT": "0.99"})
        row = result["variants"][0]["destinations"][0]
        self.assertEqual(row["state"], "pricing_configuration_invalid")
        self.assertIsNone(row["retail_estimate_usd"])

    def test_duplicates_live_mode_and_public_enable_flags_are_rejected(self):
        for change in ({"environment": "live"}, {"public_enabled": True},
                       {"requested_countries": ["IN", "IN"]},
                       {"variants": self.data["variants"] * 2}):
            with self.assertRaises(ValidationError):
                DraftCatalog.model_validate(self.data | change)

    async def test_catalog_cli_needs_no_credentials_journal_or_network(self):
        args = cli.parser().parse_args(["catalog", "--country", "US", "--store-db", str(self.db)])
        with patch.object(SandboxClient, "from_env", side_effect=AssertionError("No HTTP client allowed")), \
             patch.object(cli, "SandboxJournal", side_effect=AssertionError("No journal writes allowed")):
            result = await cli.run(args)
        self.assertEqual(result["variants"][0]["destinations"][0]["state"], "quote_required")
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
