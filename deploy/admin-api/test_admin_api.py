import hashlib
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
        ])
        self.assertEqual(calls[0].content, b'{"description":"Hand-written copy."}')

if __name__ == "__main__":
    unittest.main()
