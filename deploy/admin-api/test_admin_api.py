import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from fastapi.testclient import TestClient
import app as admin
from app import app

class FakeCJ:
    class CJError(RuntimeError):
        pass

    def __init__(self):
        self.calls = []
        self.fail = False

    async def search_products(self, keyword, page=1, size=20):
        self.calls.append(("search", keyword))
        if self.fail:
            raise self.CJError("upstream-secret")
        return {"content": [{"productList": [
            {"id": "CJ-OWNED", "nameEn": "Owned", "sellPrice": "2.00-3.00"},
            {"id": "CJ-NEW", "nameEn": "New", "sellPrice": 1.2},
            {"id": "../bad", "nameEn": "Rejected", "sellPrice": 1},
        ]}]}

    async def get_product_details(self, pid):
        self.calls.append(("details", pid))
        return {"pid": pid, "productNameEn": "New", "variants": [
            {"vid": "V1", "variantSku": "S1", "variantSellPrice": 1.2},
        ]}

async def fake_prices(costs):
    return {cost: 9.99 for cost in costs}

class AdminApiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.key = root / "key"
        self.key.write_text("a" * 40)
        self.cj_key = root / "cj"
        self.cj_key.write_text("offline-cj-key")
        self.store = root / "store.db"
        with sqlite3.connect(self.store) as db:
            db.execute("""
                CREATE TABLE products (
                    id INTEGER, slug TEXT, title TEXT, supplier TEXT,
                    price_usd REAL, active INTEGER, cj_pid TEXT, draft INTEGER
                )
            """)
            db.execute(
                "INSERT INTO products VALUES "
                "(1, 'existing', 'Existing', 'cj', 12, 1, 'CJ-OWNED', 0)"
            )
        self.before = hashlib.sha256(self.store.read_bytes()).hexdigest()
        environment = patch.dict(os.environ, {
            "CREDENTIALS_DIRECTORY": "",
            "TBW_ADMIN_KEY_FILE": str(self.key),
            "TBW_CJ_KEY_FILE": str(self.cj_key),
            "TBW_ADMIN_STORE_DB": str(self.store),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.fake = FakeCJ()
        def module():
            self.assertEqual(
                admin.credential("cj_api_key", "TBW_CJ_KEY_FILE"), "offline-cj-key"
            )
            return self.fake
        for name, value in (("retail_prices", fake_prices), ("cj_module", module)):
            patcher = patch.object(admin, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + "a" * 40}

    def tearDown(self):
        self.assertEqual(
            self.before, hashlib.sha256(self.store.read_bytes()).hexdigest()
        )

    def test_authentication(self):
        for route in ("/health", "/products", "/suppliers/cj/search?q=bookmark",
                      "/suppliers/cj/products/CJ-NEW"):
            self.assertEqual(self.client.get(route).status_code, 401)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(
            self.client.get("/health", headers=self.headers).status_code, 200
        )
        self.key.unlink()
        self.assertEqual(
            self.client.get("/health", headers=self.headers).status_code, 503
        )

    def test_cj_search_marks_owned_and_prices(self):
        response = self.client.get(
            "/suppliers/cj/search?q=bookmark", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        products = response.json()["products"]
        self.assertEqual([p["pid"] for p in products], ["CJ-OWNED", "CJ-NEW"])
        self.assertTrue(products[0]["in_store"])
        self.assertFalse(products[1]["in_store"])
        self.assertEqual(products[1]["cost_usd"], 1.2)
        self.assertEqual(products[1]["suggested_price_usd"], 9.99)
        self.assertEqual(self.fake.calls, [("search", "bookmark")])

    def test_cj_product_details(self):
        response = self.client.get(
            "/suppliers/cj/products/CJ-NEW", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["variants"][0]["suggested_price_usd"], 9.99)
        self.assertFalse(body["in_store"])
        self.assertEqual(
            self.client.get(
                "/suppliers/cj/products/bad..id", headers=self.headers
            ).status_code, 422
        )

    def test_cj_errors_are_sanitized(self):
        self.fake.fail = True
        response = self.client.get(
            "/suppliers/cj/search?q=bookmark", headers=self.headers
        )
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("upstream-secret", response.text)

    def test_cj_requires_its_credential(self):
        self.cj_key.unlink()
        self.assertEqual(
            self.client.get(
                "/suppliers/cj/search?q=bookmark", headers=self.headers
            ).status_code, 503
        )

    def test_product_reads_and_absent_write_routes(self):
        response = self.client.get("/products", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["products"][0]["slug"], "existing")
        self.assertEqual(
            self.client.post("/products", headers=self.headers, json={}).status_code,
            405,
        )
        self.assertEqual(
            self.client.post("/orders", headers=self.headers, json={}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/drafts", headers=self.headers, json={}).status_code,
            422,
        )

    def test_drafts_go_through_the_store_with_its_own_key(self):
        draft_key = self.key.parent / "draft"
        draft_key.write_text("d" * 40)
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.params.get("preview") == "true":
                return httpx.Response(200, json={"created": False, "preview": {}})
            return httpx.Response(502, json={"detail": "upstream-secret"})
        body = {"pid": "CJ-NEW", "price_usd": 19.99}
        for route in ("/drafts", "/drafts/preview"):
            self.assertEqual(self.client.post(route, json=body).status_code, 401)
        with patch.object(admin, "store_transport", httpx.MockTransport(handler)):
            self.assertEqual(self.client.post(
                "/drafts/preview", headers=self.headers, json=body
            ).status_code, 503)
            with patch.dict(os.environ, {"TBW_DRAFT_KEY_FILE": str(draft_key)}):
                self.assertEqual(self.client.post(
                    "/drafts", headers=self.headers, json={"pid": "../x"}
                ).status_code, 422)
                self.assertEqual(self.client.post(
                    "/drafts/preview", headers=self.headers, json=body
                ).json(), {"created": False, "preview": {}})
                failed = self.client.post("/drafts", headers=self.headers, json=body)
        self.assertEqual(failed.status_code, 502)
        self.assertNotIn("upstream-secret", failed.text)
        self.assertEqual(len(calls), 2)
        crosslist = lambda request: httpx.Response(502, json={"detail": "Printify POST /x: bad"})
        with patch.object(admin, "store_transport", httpx.MockTransport(crosslist)), \
                patch.dict(os.environ, {"TBW_DRAFT_KEY_FILE": str(draft_key)}):
            failed = self.client.post("/crosslist/to-etsy/38", headers=self.headers, json={})
        self.assertEqual(failed.status_code, 502)
        self.assertIn("Printify POST /x: bad", failed.text)
        for request in calls:
            self.assertEqual(str(request.url).split("?")[0],
                             "http://127.0.0.1:8010/api/internal/drafts")
            self.assertEqual(request.headers["Authorization"], "Bearer " + "d" * 40)
            self.assertNotIn("a" * 40, request.content.decode())
        self.assertEqual(self.fake.calls, [])

    def test_edit_and_publish_forward_to_the_store(self):
        draft_key = self.key.parent / "draft"
        draft_key.write_text("d" * 40)
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.path.endswith("/7/publish") and request.content:
                return httpx.Response(409, json={"detail": "Confirmation code does not match"})
            return httpx.Response(200, json={"ok": True})
        with patch.object(admin, "store_transport", httpx.MockTransport(handler)), \
                patch.dict(os.environ, {"TBW_DRAFT_KEY_FILE": str(draft_key)}):
            self.assertEqual(self.client.post(
                "/drafts/7/publish/preview", json={"code": "ABC123"}
            ).status_code, 401)
            ok = self.client.post("/drafts/7/update", headers=self.headers,
                                  json={"description": "Hand-written copy."})
            preview = self.client.post("/drafts/7/publish/preview", headers=self.headers)
            denied = self.client.post("/drafts/7/publish", headers=self.headers,
                                      json={"code": "ABC123"})
            for route, body in (("/drafts/7/delete", None),
                                ("/products/7/unpublish/preview", None),
                                ("/products/7/unpublish", {"code": "ABC123"})):
                self.assertEqual(self.client.post(
                    route, headers=self.headers, json=body
                ).status_code, 200)
            for route, body in (("/drafts/0/update", {}), ("/drafts/7/publish", {"code": "x"})):
                self.assertEqual(self.client.post(
                    route, headers=self.headers, json=body
                ).status_code, 422)
        self.assertEqual((ok.status_code, preview.status_code), (200, 200))
        self.assertEqual(denied.status_code, 409)
        self.assertIn("does not match", denied.json()["detail"])
        self.assertEqual([(r.url.path, r.url.params.get("preview")) for r in calls], [
            ("/api/internal/drafts/7/update", None),
            ("/api/internal/drafts/7/publish", "true"),
            ("/api/internal/drafts/7/publish", None),
            ("/api/internal/drafts/7/delete", None),
            ("/api/internal/products/7/unpublish", "true"),
            ("/api/internal/products/7/unpublish", None),
        ])
        self.assertEqual(json.loads(calls[2].content), {"code": "ABC123", "pin": False})
        self.assertEqual(calls[0].content, b'{"description":"Hand-written copy."}')

    def test_supplier_reads_go_through_the_store(self):
        draft_key = self.key.parent / "draft"
        draft_key.write_text("d" * 40)
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"ok": True})
        with patch.object(admin, "store_transport", httpx.MockTransport(handler)), \
                patch.dict(os.environ, {"TBW_DRAFT_KEY_FILE": str(draft_key)}):
            for route in ("/suppliers/printify/products?page=2&limit=5",
                          "/suppliers/printify/products/abc123",
                          "/suppliers/prodigi/products/GLOBAL-FAP-12X16",
                          "/products/7/shipping?country_code=MX"):
                self.assertEqual(self.client.get(route).status_code, 401)
                self.assertEqual(self.client.get(route, headers=self.headers).status_code, 200)
            for route in ("/suppliers/printify/products/a..b",
                          "/products/7/shipping?country_code=MEX"):
                self.assertEqual(self.client.get(route, headers=self.headers).status_code, 422)
        self.assertEqual([r.url.path for r in calls], [
            "/api/internal/suppliers/printify/products",
            "/api/internal/suppliers/printify/products/abc123",
            "/api/internal/suppliers/prodigi/products/GLOBAL-FAP-12X16",
            "/api/internal/shipping/7",
        ])
        self.assertEqual(json.loads(calls[0].content), {"page": 2, "limit": 5})
        self.assertEqual(json.loads(calls[3].content),
                         {"country_code": "MX", "variant_id": None, "quantity": 1})

    def test_supplier_api_goes_through_the_store(self):
        draft_key = self.key.parent / "draft"
        draft_key.write_text("d" * 40)
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.params.get("preview") == "true":
                return httpx.Response(200, json={"executed": False, "code": "ABC123"})
            return httpx.Response(403, json={"detail": "Orders and payments are disabled"})
        body = {"method": "POST", "path": "/orders", "body": {}}
        with patch.object(admin, "store_transport", httpx.MockTransport(handler)), \
                patch.dict(os.environ, {"TBW_DRAFT_KEY_FILE": str(draft_key)}):
            self.assertEqual(self.client.post("/suppliers/prodigi/api", json=body).status_code, 401)
            self.assertEqual(self.client.post("/suppliers/amazon/api", headers=self.headers,
                                              json=body).status_code, 422)
            preview = self.client.post("/suppliers/prodigi/api?preview=true",
                                       headers=self.headers, json=body)
            blocked = self.client.post("/suppliers/prodigi/api", headers=self.headers, json=body)
        self.assertEqual(preview.json()["code"], "ABC123")
        self.assertEqual(blocked.status_code, 403)
        self.assertIn("disabled", blocked.json()["detail"])
        self.assertEqual([r.url.path for r in calls], ["/api/internal/suppliers/prodigi/api"] * 2)
        self.assertEqual(json.loads(calls[0].content),
                         {"method": "POST", "path": "/orders", "body": {}, "code": None})

    def test_crosslist_goes_through_the_store(self):
        draft_key = self.key.parent / "draft"
        draft_key.write_text("d" * 40)
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"ok": True})
        with patch.object(admin, "store_transport", httpx.MockTransport(handler)), \
                patch.dict(os.environ, {"TBW_DRAFT_KEY_FILE": str(draft_key)}):
            self.assertEqual(self.client.post("/crosslist/from-etsy", json={"listing_id": "42"}).status_code, 401)
            for route, body in (("/crosslist/from-etsy?preview=true", {"listing_id": "42"}),
                                ("/crosslist/to-etsy/7", {"taxonomy_id": 2078, "code": "ABC123"})):
                self.assertEqual(self.client.post(route, headers=self.headers, json=body).status_code, 200)
            self.assertEqual(self.client.post("/crosslist/from-etsy", headers=self.headers,
                                              json={"listing_id": "x"}).status_code, 422)
        self.assertEqual([(r.url.path, r.url.params.get("preview")) for r in calls], [
            ("/api/internal/crosslist/from-etsy", "true"), ("/api/internal/crosslist/to-etsy/7", None)])
        self.assertEqual(json.loads(calls[1].content),
                         {"taxonomy_id": 2078, "price_usd": None, "extra": None, "code": "ABC123"})

    def activity_fixture(self):
        with sqlite3.connect(self.store) as db:
            db.execute("ALTER TABLE products ADD COLUMN created_at TEXT")
            db.execute("ALTER TABLE products ADD COLUMN etsy_listing_id TEXT")
            db.execute("UPDATE products SET created_at='2026-10-29 02:59:59', etsy_listing_id='42'")
            db.execute("""CREATE TABLE product_publication_events (
                id INTEGER PRIMARY KEY, product_id INTEGER, product_slug TEXT,
                product_title TEXT, platform TEXT, event_type TEXT, occurred_at TEXT, source TEXT)""")
            db.executemany("INSERT INTO product_publication_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (1, 0, '', '', 'store', 'tracking_started', '2026-10-28 00:00:00', 'schema_created'),
                (2, 1, 'existing', 'Original title', 'store', 'published', '2026-10-29 03:00:00', 'visibility_change'),
                (3, 1, 'existing', 'Original title', 'store', 'unpublished', '2026-10-30 03:00:00', 'visibility_change'),
            ])
            db.execute("""CREATE TABLE pinterest_pins (id INTEGER, product_id INTEGER,
                product_slug TEXT, pin_id TEXT, status TEXT, created_at TEXT, error TEXT)""")
            db.executemany("INSERT INTO pinterest_pins VALUES (?,1,'existing',?,?,?,?)", [
                (1, '123', 'active', '2026-10-29 23:00:00', ''),
                (2, '', 'failed', '2026-10-29 23:00:00', 'never return this error'),
                (3, '123', 'duplicate', '2026-10-29 23:00:00', ''),
            ])
        self.before = hashlib.sha256(self.store.read_bytes()).hexdigest()

    def test_product_dates_and_activity_use_local_day_and_no_creation_inference(self):
        self.activity_fixture()
        product = self.client.get('/products', headers=self.headers).json()['products'][0]
        self.assertEqual(product['created_at'], '2026-10-29T02:59:59Z')
        self.assertEqual(product['etsy_listing_id'], '42')
        self.assertIsNone(product['published_at'])
        self.assertEqual(product['last_recorded_publication_at'], '2026-10-29T03:00:00Z')
        response = self.client.get('/products/activity?day=2026-10-29&limit=1', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data['start_utc'], data['end_utc_exclusive']),
                         ('2026-10-29T03:00:00Z', '2026-10-30T03:00:00Z'))
        self.assertEqual(data['total'], 2)
        self.assertTrue(data['has_more'])
        self.assertEqual(data['events'][0]['event_type'], 'published')
        self.assertEqual(data['events'][0]['title'], 'Original title')
        page = self.client.get('/products/activity?day=2026-10-29&limit=1&offset=1', headers=self.headers).json()
        self.assertFalse(page['has_more'])
        self.assertEqual(page['events'][0]['event_type'], 'pin_recorded')
        self.assertNotIn('never return this error', str(page))
        self.assertEqual(page['coverage']['store_tracking_started_at'], '2026-10-28T00:00:00Z')

    def test_activity_validates_and_reports_missing_tracking(self):
        self.assertEqual(self.client.get('/products/activity?day=2026-10-29').status_code, 401)
        for query in ('day=bad', 'day=2026-02-30', 'day=2026-10-29&timezone=Missing/Zone',
                      'day=2026-10-29&platform=etsy', 'day=2026-10-29&limit=101', 'day=9999-12-31'):
            self.assertEqual(self.client.get('/products/activity?' + query, headers=self.headers).status_code, 422)
        data = self.client.get('/products/activity?day=2026-10-29', headers=self.headers).json()
        self.assertEqual(data['events'], [])
        self.assertFalse(data['coverage']['store_ledger_available'])
        self.assertIsNone(data['coverage']['store_tracking_started_at'])

    def test_activity_filters_and_santiago_dst_window(self):
        self.activity_fixture()
        data = self.client.get('/products/activity?day=2026-10-29&platform=store', headers=self.headers).json()
        self.assertEqual([e['event_type'] for e in data['events']], ['published'])
        data = self.client.get('/products/activity?day=2026-10-29&product_id=999', headers=self.headers).json()
        self.assertEqual(data['total'], 0)
        data = self.client.get('/products/activity?day=2026-09-06', headers=self.headers).json()
        self.assertEqual((data['start_utc'], data['end_utc_exclusive']),
                         ('2026-09-06T04:00:00Z', '2026-09-07T03:00:00Z'))

    def test_etsy_listing_metadata_uses_authenticated_read_proxy(self):
        draft_key = self.key.parent / 'draft'
        draft_key.write_text('d' * 40)
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'listings': [], 'total': 0})
        with patch.object(admin, 'store_transport', httpx.MockTransport(handler)), \
                patch.dict(os.environ, {'TBW_DRAFT_KEY_FILE': str(draft_key)}):
            self.assertEqual(self.client.get('/suppliers/etsy/listings').status_code, 401)
            response = self.client.get('/suppliers/etsy/listings?state=draft&limit=2&offset=3', headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get('/suppliers/etsy/listings?state=all', headers=self.headers).status_code, 422)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url.path, '/api/internal/suppliers/etsy/listings')
        self.assertEqual(calls[0].headers['Authorization'], 'Bearer ' + 'd' * 40)
        self.assertEqual(json.loads(calls[0].content), {'state': 'draft', 'limit': 2, 'offset': 3})

if __name__ == "__main__":
    unittest.main()
