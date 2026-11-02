"""Offline checks for Bonanza orders: SKU matching, order parsing, drafts before charges,
approval charging once, and nothing sent for orders that cannot be matched."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import BonanzaOrder, SlantSubmission
from services import bonanza, bonanza_orders as flow

ENV = {"SLANT3D_API_KEY": "sl_offline", "SLANT3D_PLATFORM_ID": "4e24626a-75da-440f-95a5-9cfe079256d3",
       "SLANT3D_ORDERS_ENABLED": "1", "SLANT3D_CONTACT_EMAIL": "shop@example.com"}
ADDRESS = {"name": "Ada Lovelace", "street1": "1 Main St", "street2": "", "cityName": "Albany",
           "stateOrProvince": "NY", "postalCode": "12207", "country": "US"}


def order(oid="777", items=None, **extra):
    o = {"orderID": oid, "orderStatus": "Completed", "paidTime": "2026-11-04T10:00:00Z", "total": "46.99",
         "shippingAddress": ADDRESS,
         "itemArray": [{"item": i} for i in (items or [{"sku": "TBW-PP-SWEAT-SAND-M", "quantity": 1, "title": "Sweatshirt"}])]}
    o.update(extra)
    return o


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.cfg = flow.config()

    def test_variation_sku_and_parent_with_options(self):
        leg = flow.resolve(self.cfg, {"sku": "TBW-PP-SWEAT-LIGHTBLUE-2XL", "quantity": 1, "attributes": {}})
        self.assertEqual((leg["supplier"], leg["variant_id"]), ("printify", 25509))
        leg = flow.resolve(self.cfg, {"sku": "TBW-PP-SWEAT", "quantity": 2, "attributes": {"color": "white", "Size": "M"}})
        self.assertEqual((leg["variant_id"], leg["quantity"]), (25427, 2))
        leg = flow.resolve(self.cfg, {"sku": "TBW-ORN-SET", "quantity": 1, "attributes": {"Set": "All gold"}})
        self.assertEqual((leg["supplier"], leg["sku"]), ("slant3d", "TBW-ORN-SET-GOLD"))
        self.assertEqual(flow.resolve(self.cfg, {"sku": "TBW-PP-MUG", "quantity": 1, "attributes": {}})["variant_id"], 33719)

    def test_unknown_or_ambiguous_lines_are_refused(self):
        for line in [{"sku": "MRBN-ulam-43135", "quantity": 1, "attributes": {}},
                     {"sku": "TBW-PP-SWEAT", "quantity": 1, "attributes": {"Color": "Sand"}},
                     {"sku": "TBW-PP-MUG", "quantity": 0, "attributes": {}},
                     {"sku": "", "quantity": 1, "attributes": {}}]:
            with self.assertRaises(ValueError):
                flow.resolve(self.cfg, line)

    def test_every_sweatshirt_variant_is_mapped_once(self):
        ids = [v["variant_id"] for v in self.cfg["products"]["TBW-PP-SWEAT"]["variants"].values()]
        self.assertEqual(len(ids), 20)
        self.assertEqual(len(set(ids)), 20)


class ParsingTests(unittest.TestCase):
    def test_orders_items_address_and_states(self):
        data = {"getOrdersResponse": {"orderArray": [{"order": order(items=[
            {"sku": "TBW-ORN-SET", "quantity": "1", "title": "Ornaments",
             "variation": {"nameValueList": [{"name": "Set", "value": "All gold"}]}}])}]}}
        [o] = bonanza.orders(data)
        self.assertEqual(bonanza.order_id(o), "777")
        self.assertTrue(bonanza.is_paid(o))
        self.assertFalse(bonanza.is_shipped(o))
        self.assertEqual(bonanza.items(o)[0]["attributes"], {"Set": "All gold"})
        self.assertEqual(bonanza.address(o)["country"], "US")
        self.assertNotIn("Ada", json.dumps(bonanza.shape(o)))
        self.assertTrue(bonanza.is_shipped({**o, "orderStatus": "Shipped"}))
        self.assertFalse(bonanza.is_paid({"orderStatus": "Active"}))


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV); self.env.start(); self.addCleanup(self.env.stop)
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.cfg = flow.config()

    async def test_printify_order_is_made_on_hold_and_charged_only_on_approval(self):
        with patch.object(flow.printify, "create_order", AsyncMock(return_value={"id": "pf1"})) as create, \
             patch.object(flow.printify, "get_order", AsyncMock(return_value={"total_price": 1870, "total_shipping": 919})), \
             patch.object(flow.printify, "send_to_production", AsyncMock(return_value={})) as produce:
            row = await flow.prepare(self.db, self.cfg, order())
            self.assertEqual((row.state, row.cost_usd), ("awaiting", 27.89))
            self.assertEqual(create.await_args.kwargs["shop"], "29520280")
            produce.assert_not_awaited()
            again = await flow.prepare(self.db, self.cfg, order())
            self.assertEqual(create.await_count, 1)
            self.assertIs(again, row)
            await flow.approve(self.db, row)
            with self.assertRaises(ValueError):
                await flow.approve(self.db, row)
            self.assertEqual(produce.await_count, 1)
            self.assertEqual(row.state, "approved")

    async def test_slant_draft_is_free_until_approved(self):
        drafted = {"publicId": "SLANT_1000000009", "status": "DRAFT", "printingCost": "6.29", "deliveryCost": "7.08"}
        with patch.object(flow.slant3d, "request", AsyncMock(return_value=drafted)) as req, \
             patch.object(flow.slant3d_submission, "submit", AsyncMock(return_value="SLANT_1000000009")) as submit:
            row = await flow.prepare(self.db, self.cfg, order(items=[{"sku": "TBW-ORN-SET-CLASSIC", "quantity": 1}]))
            self.assertEqual(row.state, "awaiting")
            self.assertEqual([c.args[:2] for c in req.await_args_list], [("POST", "/orders")])
            self.assertEqual(self.db.get(SlantSubmission, row.ref).state, "drafted")
            submit.assert_not_awaited()
            await flow.approve(self.db, row)
            submit.assert_awaited_once()

    async def test_unmatched_order_goes_to_review_without_any_supplier_call(self):
        with patch.object(flow.printify, "create_order", AsyncMock()) as create, \
             patch.object(flow.slant3d, "request", AsyncMock()) as req:
            row = await flow.prepare(self.db, self.cfg, order(oid="8", items=[{"sku": "MRBN-ulam-43135", "quantity": 1}]))
            bad = await flow.prepare(self.db, self.cfg, order(oid="9", shippingAddress={**ADDRESS, "street1": ""}))
        self.assertEqual((row.state, bad.state), ("review", "review"))
        create.assert_not_awaited()
        req.assert_not_awaited()
        with self.assertRaises(ValueError):
            await flow.approve(self.db, row)

    async def test_shipped_order_is_marked_on_bonanza_once(self):
        row = BonanzaOrder(ref="bonanza-5", state="approved", summary_json=json.dumps({"order_id": "5"}),
                           legs_json=json.dumps([{"supplier": "printify", "printify_order_id": "pf5"}]))
        self.db.add(row); self.db.commit()
        shipped = {"shipments": [{"carrier": "usps", "number": "9400", "url": "https://t"}]}
        with patch.object(flow.printify, "get_order", AsyncMock(return_value=shipped)), \
             patch.object(flow.bonanza, "call", AsyncMock(return_value={})) as call:
            result = await flow.sync(self.db, row)
        self.assertTrue(result.startswith("posted"))
        self.assertEqual(row.state, "shipped")
        self.assertEqual(call.await_args.args[0], "/completeSaleRequest")
        self.assertEqual(call.await_args.kwargs["key"], "tbw-bonanza-5-shipped")


if __name__ == "__main__":
    unittest.main()
