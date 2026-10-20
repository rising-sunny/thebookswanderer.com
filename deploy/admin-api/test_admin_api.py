import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import app

class AdminApiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.catalog = root / "catalog.json"
        self.key = root / "key"
        self.key.write_text("a" * 40)
        self.store = root / "store.db"
        with sqlite3.connect(self.store) as db:
            db.execute("""
                CREATE TABLE products (
                    id INTEGER, slug TEXT, title TEXT, supplier TEXT,
                    price_usd REAL, active INTEGER
                )
            """)
            db.execute(
                "INSERT INTO products VALUES (1, 'existing', 'Existing', 'cj', 12, 1)"
            )
        self.before = hashlib.sha256(self.store.read_bytes()).hexdigest()
        environment = patch.dict(os.environ, {
            "CREDENTIALS_DIRECTORY": "",
            "TBW_ADMIN_KEY_FILE": str(self.key),
            "TBW_ADMIN_DRAFT_DB": str(root / "drafts.db"),
            "TBW_ADMIN_STORE_DB": str(self.store),
            "TBW_QIKINK_CATALOG_FILE": str(self.catalog),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + "a" * 40}
        self.payload = {
            "reference": "offline_test",
            "slug": "offline-test",
            "title": "Offline test",
            "variants": [{"name": "Small", "qikink_sku": "TEST-S"}],
        }

    def tearDown(self):
        self.assertEqual(
            self.before, hashlib.sha256(self.store.read_bytes()).hexdigest()
        )

    def test_catalog_read_only_search(self):
        snapshot = {
            "schema_version": 1, "source": "offline-test-fixture",
            "retrieved_at": "2026-01-01T00:00:00Z",
            "variants": [
                {"product_title": "Bookmark", "name": "Classic",
                 "qikink_sku": "FIXTURE-Classic", "sku_kind": "product"},
                {"product_title": "Bookmark", "name": "Curved Top",
                 "qikink_sku": "FIXTURE-Curved", "sku_kind": "store"},
            ],
        }
        self.catalog.write_text(json.dumps(snapshot))
        before = self.catalog.read_bytes()
        self.assertEqual(self.client.get("/qikink/catalog").status_code, 401)
        response = self.client.get("/qikink/catalog", headers=self.headers,
                                   params={"query": "BOOKMARK classic"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["variants"][0]["qikink_sku"], "FIXTURE-Classic")
        self.assertFalse(data["live_verified"])
        response = self.client.get("/qikink/catalog", headers=self.headers,
                                   params={"sku": "fixture-classic"})
        self.assertEqual(response.json()["total"], 0)
        response = self.client.get("/qikink/catalog", headers=self.headers,
                                   params={"limit": 1, "offset": 1})
        self.assertEqual(response.json()["variants"][0]["sku_kind"], "store")
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertEqual(self.client.post("/qikink/catalog", headers=self.headers,
                                         json={}).status_code, 405)
        self.assertEqual(self.client.get("/qikink/catalog", headers=self.headers,
                                         params={"limit": 101}).status_code, 422)

    def test_catalog_unavailable_or_invalid_is_not_empty(self):
        for content in [None, "not-json", json.dumps({"schema_version": 1}),
                        "x" * 5_000_001]:
            if content is not None:
                self.catalog.write_text(content)
            response = self.client.get("/qikink/catalog", headers=self.headers)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(str(self.catalog), response.text)

    def test_catalog_rejects_ambiguous_or_unattributed_data(self):
        base = {"schema_version": 1, "source": "offline-test-fixture",
                "retrieved_at": "2026-01-01T00:00:00Z", "variants": []}
        variant = {"product_title": "Bookmark", "name": "Classic",
                   "qikink_sku": "FIXTURE", "sku_kind": "product"}
        for change in [
            {"retrieved_at": "2026-01-01T00:00:00"},
            {"retrieved_at": "2999-01-01T00:00:00Z"},
            {"variants": [variant, variant]},
            {"variants": [{**variant, "sku_kind": "unknown"}]},
            {"source": " "}, {"credentials": "must-not-leak"},
        ]:
            self.catalog.write_text(json.dumps({**base, **change}))
            response = self.client.get("/qikink/catalog", headers=self.headers)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("must-not-leak", response.text)
        self.catalog.write_text(json.dumps(base))
        self.assertEqual(self.client.get("/qikink/catalog", headers=self.headers)
                         .json()["total"], 0)

    def test_authentication(self):
        for route in ("/health", "/products", "/drafts"):
            self.assertEqual(self.client.get(route).status_code, 401)
        self.assertEqual(
            self.client.post("/drafts", json=self.payload).status_code, 401
        )
        self.assertEqual(
            self.client.get("/health", headers=self.headers).status_code, 200
        )
        self.key.unlink()
        self.assertEqual(
            self.client.get("/health", headers=self.headers).status_code, 503
        )

    def test_draft_idempotence_and_conflict(self):
        response = self.client.post(
            "/drafts", headers=self.headers, json=self.payload
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["public_sales_enabled"])
        self.assertFalse(response.json()["order_submission_enabled"])
        self.assertEqual(
            self.client.post(
                "/drafts", headers=self.headers, json=self.payload
            ).status_code, 200
        )
        changed = dict(self.payload, title="Changed")
        self.assertEqual(
            self.client.post(
                "/drafts", headers=self.headers, json=changed
            ).status_code, 409
        )
        saved = self.client.get("/drafts/offline_test", headers=self.headers)
        self.assertEqual(saved.json()["draft"]["title"], "Offline test")
        self.assertEqual(
            len(self.client.get("/drafts", headers=self.headers).json()["drafts"]),
            1,
        )

    def test_publication_fields_and_remote_images_rejected(self):
        for changed in (
            dict(self.payload, active=True),
            dict(self.payload, supplier="cj"),
            dict(self.payload, variants=[{
                "name": "Small", "qikink_sku": "TEST-S",
                "design_image": "https://example.com/image.png",
            }]),
        ):
            self.assertEqual(
                self.client.post(
                    "/drafts", headers=self.headers, json=changed
                ).status_code, 422
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

if __name__ == "__main__":
    unittest.main()
