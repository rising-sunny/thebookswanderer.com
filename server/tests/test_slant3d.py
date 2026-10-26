"""Offline checks for Slant 3D: transport allowlist, once-only charge, cost cap, Etsy mapping."""
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER)); sys.path.insert(0, str(SERVER / "scripts"))
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Order, OrderItem, Product, ProductVariant, SlantSubmission
from services import shipping, slant3d as s, slant3d_submission as sub

ENV = {"SLANT3D_API_KEY": "sl_offline", "SLANT3D_PLATFORM_ID": "4e24626a-75da-440f-95a5-9cfe079256d3",
       "SLANT3D_ORDERS_ENABLED": "1", "SLANT3D_CONTACT_EMAIL": "shop@example.com"}
SLUG = s.spec()["products"][0]["slug"]


def order(publicId="SLANT_1000000001", status="DRAFT", printing="6.40", delivery="7.02"):
    return {"publicId": publicId, "status": status, "printingCost": printing, "deliveryCost": delivery}


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV); self.env.start(); self.addCleanup(self.env.stop)

    async def test_only_drafts_reads_and_processing_reach_slant(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"success": True, "data": {"order": order()}})
        t = httpx.MockTransport(handler)
        for method, path in [("GET", "/files"), ("DELETE", "/orders/SLANT_1000000001"), ("GET", "https://example.com"),
                             ("POST", "/orders/../apiKey")]:
            with self.assertRaises(s.Slant3DError):
                await s.request(method, path, transport=t)
        with patch.dict(os.environ, {"SLANT3D_ORDERS_ENABLED": "0"}):
            with self.assertRaises(s.Slant3DError):
                await s.request("POST", "/orders/SLANT_1000000001", transport=t)
        self.assertEqual(calls, [])
        self.assertEqual((await s.request("POST", "/orders", {}, transport=t))["publicId"], "SLANT_1000000001")
        self.assertEqual(calls[0].headers["authorization"], "Bearer sl_offline")

    async def test_errors_never_carry_the_key(self):
        t = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "sl_offline bad"}))
        with self.assertRaises(s.Slant3DError) as error:
            await s.request("GET", "/orders/SLANT_1000000001", transport=t)
        self.assertNotIn("sl_offline", str(error.exception))

    def test_lines_come_from_the_manifest_only(self):
        lines = s.lines(SLUG, 2, "TBW-HYPERBOLOID-GOLD")
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(s.lines(SLUG, 1, "TBW-HYPERBOLOID-RAINBOW")), 1)
        self.assertEqual({l["type"] for l in lines}, {"PRINT"})
        self.assertEqual([l["quantity"] for l in lines], [2] * len(lines))
        for bad in (0, 11, True, "1"):
            with self.assertRaises(s.Slant3DError):
                s.lines(SLUG, bad)
        with self.assertRaises(s.Slant3DError):
            s.lines("not-reviewed", 1)
        with self.assertRaises(s.Slant3DError):
            s.lines(SLUG, 1)          # two colours: the SKU must say which
        with self.assertRaises(s.Slant3DError):
            s.lines(SLUG, 1, "TBW-OTHER")

    def test_customer_needs_shop_email_full_address_and_a_served_country(self):
        c = s.customer("Ann Reader", "1 Main St", "", "Boston", "MA", "02108", "us")
        self.assertEqual(c["details"]["email"], "shop@example.com")
        self.assertEqual(c["details"]["address"]["country"], "US")
        with self.assertRaises(s.Slant3DError):
            s.customer("Ann Reader", "1 Rua A", "", "Sao Paulo", "SP", "01000-000", "BR")
        with self.assertRaises(s.Slant3DError):
            s.customer("Ann Reader", "", "", "Boston", "MA", "02108", "US")
        with patch.dict(os.environ, {"SLANT3D_CONTACT_EMAIL": ""}):
            with self.assertRaises(s.Slant3DError):
                s.customer("Ann Reader", "1 Main St", "", "Boston", "MA", "02108", "US")

    def test_tracking_is_found_in_the_fulfillment_block(self):
        o = order(status="SHIPPED")
        o["fulfillment"] = {"shipments": [{"carrier": "USPS", "trackingNumber": "9400111", "trackingUrl": "https://t.example/9400111"}]}
        self.assertEqual(s.tracking(o), ("USPS", "9400111", "https://t.example/9400111"))
        self.assertEqual(s.tracking(order()), ("", "", ""))


class CheckoutTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV); self.env.start(); self.addCleanup(self.env.stop)
        self.product = Product(slug=SLUG, title="Hyperboloid", supplier="slant3d", price_usd=39.99)

    async def test_us_shipping_is_included_and_unserved_countries_are_refused(self):
        cart = [(self.product, SimpleNamespace(cj_sku="TBW-HYPERBOLOID-GOLD", price_usd=39.99), 1)]
        us = await shipping.quote(cart, "US", {"street1": "1 Main St", "city": "Boston"})
        self.assertEqual(us["shipping_total"], 0.0)
        gb = await shipping.quote(cart, "GB", {"street1": "1 High St", "city": "London"})
        self.assertEqual(gb["shipping_total"], s.spec()["shipping"]["international"])
        with self.assertRaises(shipping.QuoteError):
            await shipping.quote(cart, "BR", {"street1": "1 Rua A", "city": "Sao Paulo"})


class SubmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV); self.env.start(); self.addCleanup(self.env.stop)
        self.engine = create_engine("sqlite://"); Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.addCleanup(self.engine.dispose); self.addCleanup(self.db.close)
        cust = s.customer("Ann Reader", "1 Main St", "", "Boston", "MA", "02108", "US")
        self.claim = sub.prepare(self.db, "web-1", s.draft_payload("web-1", s.lines(SLUG, 1, "TBW-HYPERBOLOID-GOLD"), cust), 18.0)

    async def test_draft_then_one_charge_and_the_claim_precedes_it(self):
        seen = []
        async def respond(method, path, payload=None, transport=None):
            seen.append((method, path))
            if path == "/orders":
                self.assertEqual(payload["metadata"], {"tbw_ref": "web-1"})
                return order()
            self.db.refresh(self.claim); self.assertEqual(self.claim.state, "processing")
            return order(status="PAID")
        with patch.object(s, "request", AsyncMock(side_effect=respond)):
            self.assertEqual(await sub.submit(self.db, self.claim), "SLANT_1000000001")
            self.assertEqual(await sub.submit(self.db, self.claim), "SLANT_1000000001")
        self.assertEqual(seen, [("POST", "/orders"), ("POST", "/orders/SLANT_1000000001")])
        self.assertEqual(self.claim.cost_usd, 13.42)

    async def test_cost_above_the_cap_is_held_and_never_charged(self):
        with patch.object(s, "request", AsyncMock(return_value=order(delivery="25.32"))) as request:
            with self.assertRaises(s.Slant3DError):
                await sub.submit(self.db, self.claim)
            with self.assertRaises(s.Slant3DError):
                await sub.submit(self.db, self.claim)
        self.assertEqual(request.await_count, 1)
        self.assertEqual(self.claim.state, "review")

    async def test_unclear_charge_is_reconciled_not_resent(self):
        async def respond(method, path, payload=None, transport=None):
            if path == "/orders":
                return order()
            raise s.Slant3DError("timeout")
        with patch.object(s, "request", AsyncMock(side_effect=respond)):
            with self.assertRaises(s.Slant3DError):
                await sub.submit(self.db, self.claim)
        self.assertEqual(self.claim.state, "uncertain")
        with patch.object(s, "request", AsyncMock()) as request:
            with self.assertRaises(s.Slant3DError):
                await sub.submit(self.db, self.claim)
            request.assert_not_awaited()
        with patch.object(s, "request", AsyncMock(return_value=order(status="PAID"))):
            self.assertEqual(await sub.reconcile(self.db, self.claim), "submitted")

    async def test_a_draft_that_was_never_charged_can_be_processed_again(self):
        self.claim.draft_id, self.claim.cost_usd, self.claim.state = "SLANT_1000000001", 13.42, "uncertain"
        self.db.commit()
        with patch.object(s, "request", AsyncMock(return_value=order())):
            self.assertEqual(await sub.reconcile(self.db, self.claim), "drafted")

    async def test_disabled_ordering_sends_nothing(self):
        with patch.dict(os.environ, {"SLANT3D_ORDERS_ENABLED": "0"}), patch.object(s, "request", AsyncMock()) as request:
            with self.assertRaises(s.Slant3DError):
                await sub.submit(self.db, self.claim)
            request.assert_not_awaited()

    async def test_store_order_goes_to_slant_and_not_to_cj(self):
        import main
        product = Product(slug=SLUG, title="Hyperboloid", supplier="slant3d", price_usd=39.99)
        self.db.add(product); self.db.flush()
        variant = ProductVariant(product_id=product.id, name="Gold on matte black", cj_sku="TBW-HYPERBOLOID-GOLD")
        self.db.add(variant); self.db.flush()
        o = Order(status="paid", paypal_order_id="P1", customer_name="Ann Reader", email="ann@example.com",
                  shipping_address="1 Main St", shipping_city="Boston", shipping_province="MA",
                  shipping_zip="02108", shipping_country_code="US")
        self.db.add(o); self.db.flush()
        self.db.add(OrderItem(order_id=o.id, product_id=product.id, variant_id=variant.id, quantity=1, unit_price=39.99)); self.db.commit()
        responses = [order(publicId="SLANT_1000000002"), order(publicId="SLANT_1000000002", status="PAID")]
        with patch.object(s, "request", AsyncMock(side_effect=responses)) as request, \
                patch.object(main, "_submit_to_cj", AsyncMock()) as cj, \
                patch.object(main.email_service, "send_order_fulfillment_started", AsyncMock()):
            await main._fulfil(o, self.db)
        cj.assert_not_awaited()
        self.assertEqual(request.await_count, 2)
        self.assertEqual(o.slant_order_id, "SLANT_1000000002")
        self.assertEqual(o.status, "cj_submitted")
        payload = request.await_args_list[0].args[2]
        self.assertEqual(payload["customer"]["details"]["email"], "shop@example.com")


class EtsyTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV); self.env.start(); self.addCleanup(self.env.stop)

    def test_receipt_lines_map_only_listed_3d_prints(self):
        import etsy_slant_fulfill as worker
        spec = s.spec(); spec["products"][0]["etsy_listing_id"] = "4600000001"
        receipt = {"receipt_id": 77, "name": "Ann Reader", "first_line": "1 Main St", "second_line": "",
                   "city": "Boston", "state": "MA", "zip": "02108", "country_iso": "US",
                   "transactions": [{"listing_id": 4600000001, "quantity": 2, "sku": "TBW-HYPERBOLOID-RAINBOW"},
                                    {"listing_id": 123, "quantity": 1, "sku": "OTHER"}]}
        with patch.object(s, "spec", return_value=spec):
            wanted = worker.receipt_lines(receipt)
            self.assertEqual(wanted, [(SLUG, 2, "TBW-HYPERBOLOID-RAINBOW")])
            ref, payload, cap = worker.payload_for(receipt, wanted)
        self.assertEqual(ref, "etsy-77")
        self.assertEqual(payload["metadata"], {"tbw_ref": "etsy-77"})
        self.assertEqual(cap, spec["products"][0]["max_cost_us"] * 2)
        self.assertEqual([(i["SKU"], i["quantity"]) for i in payload["items"]], [("TBW-HYPERBOLOID-RAINBOW", 2)])



class PublicationTests(unittest.TestCase):
    def test_stage_maps_each_colour_to_its_reviewed_sku(self):
        import publish_slant3d_products as pub
        engine = create_engine("sqlite://"); Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, autoflush=False)()
        data = s.product_spec(SLUG)
        pub.check(data)
        product = pub.stage(db, data, publish=True); db.commit()
        self.assertEqual(product.supplier, "slant3d")
        self.assertTrue(product.active)
        self.assertEqual(sorted(v.cj_sku for v in product.variants), sorted(v["sku"] for v in data["variants"]))
        pub.stage(db, data, publish=True); db.commit()
        self.assertEqual(len(product.variants), len(data["variants"]))
        for v in product.variants:
            self.assertTrue(s.lines(SLUG, 1, v.cj_sku))
        db.close(); engine.dispose()


if __name__ == "__main__":
    unittest.main()
