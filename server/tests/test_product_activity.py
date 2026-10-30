"""Offline publication receipts and safe Etsy listing metadata."""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from database import Base
from fastapi.testclient import TestClient
from models import Product, ProductPublicationEvent
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


class PublicationReceipts(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

    def receipts(self):
        return self.db.scalars(select(ProductPublicationEvent).where(
            ProductPublicationEvent.event_type != "tracking_started"
        ).order_by(ProductPublicationEvent.id)).all()

    def test_draft_is_not_publication_and_republication_is_retained(self):
        p = Product(slug="book", title="Book", active=False, draft=True)
        self.db.add(p)
        self.db.commit()
        self.assertEqual(self.receipts(), [])
        p.active, p.draft = True, False
        self.db.commit()
        p.title = "Updated book"
        self.db.commit()
        p.active, p.draft = False, True
        self.db.commit()
        p.active, p.draft = True, False
        self.db.commit()
        self.assertEqual([r.event_type for r in self.receipts()],
                         ["published", "unpublished", "published"])
        self.assertEqual([r.product_title for r in self.receipts()],
                         ["Book", "Updated book", "Updated book"])

    def test_new_live_product_receipt_is_transactional(self):
        self.db.add(Product(slug="book", title="Book"))
        self.db.flush()
        self.assertEqual([r.event_type for r in self.receipts()], ["published"])
        self.db.rollback()
        self.assertEqual(self.receipts(), [])

    def test_deleted_product_keeps_history(self):
        p = Product(slug="book", title="Book")
        self.db.add(p)
        self.db.commit()
        product_id = p.id
        self.db.delete(p)
        self.db.commit()
        self.assertEqual([r.event_type for r in self.receipts()], ["published", "unpublished"])
        self.assertTrue(all(r.product_id == product_id for r in self.receipts()))
        Base.metadata.create_all(self.engine)
        self.assertEqual(self.db.query(ProductPublicationEvent).filter_by(
            event_type="tracking_started").count(), 1)

    def test_upgrade_does_not_invent_publications_for_existing_products(self):
        ProductPublicationEvent.__table__.drop(self.engine)
        with self.engine.begin() as connection:
            connection.execute(Product.__table__.insert().values(
                slug='existing', title='Existing', active=True, draft=False,
                created_at=datetime(2020, 1, 1),
            ))
        Base.metadata.create_all(self.engine)
        self.assertEqual(self.receipts(), [])
        self.assertEqual(self.db.query(Product).one().created_at, datetime(2020, 1, 1))


class EtsyMetadata(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        key = Path(temp.name) / "key"
        key.write_text("k" * 40)
        env = patch.dict(os.environ, {"TBW_DRAFT_KEY_FILE": str(key), "ETSY_SHOP_ID": "300"})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + "k" * 40}
        self.query = AsyncMock(return_value={"count": 2, "results": [{
            "shop_id": 300, "listing_id": 42, "title": "Book", "state": "active",
            "original_creation_timestamp": 1600000000, "creation_timestamp": 1700000000,
            "state_timestamp": 1750000000, "last_modified_timestamp": 1760000000,
            "url": "https://untrusted.example", "access_token": "not-for-output",
        }]})
        mock = patch.object(main.crosslist, "_etsy", self.query)
        mock.start()
        self.addCleanup(mock.stop)

    def post(self, headers=None, **body):
        return self.client.post("/api/internal/suppliers/etsy/listings", json=body,
                                headers=self.headers if headers is None else headers)

    def test_auth_and_proxy_guard_before_etsy(self):
        self.assertEqual(self.post(headers={}).status_code, 401)
        self.assertEqual(self.post(headers={**self.headers, "X-Forwarded-For": "203.0.113.1"}).status_code, 404)
        self.query.assert_not_awaited()

    def test_dates_are_distinct_and_only_safe_fields_escape(self):
        result = self.post(limit=1).json()
        item = result["listings"][0]
        self.assertNotEqual(item["original_created_at"], item["created_or_renewed_at"])
        self.assertIsNone(item["first_published_at"])
        self.assertEqual(item["url"], "https://www.etsy.com/listing/42")
        self.assertNotIn("not-for-output", str(result))
        self.assertTrue(result["has_more"])
        self.query.assert_awaited_once_with("GET", "/application/shops/300/listings", params={
            "state": "active", "limit": 1, "offset": 0, "sort_on": "created", "sort_order": "desc",
        })

    def test_foreign_shop_and_errors_are_rejected(self):
        self.query.return_value["results"][0]["shop_id"] = 999
        self.assertEqual(self.post().status_code, 502)
        self.query.side_effect = main.crosslist.CrossListError("supplier-secret")
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("supplier-secret", response.text)

    def test_invalid_input_and_missing_shop_do_not_contact_etsy(self):
        for body in ({"state": "all"}, {"limit": 101}, {"offset": -1}):
            self.assertEqual(self.post(**body).status_code, 422)
        with patch.dict(os.environ, {"ETSY_SHOP_ID": ""}):
            self.assertEqual(self.post().status_code, 503)
        self.query.assert_not_awaited()

    def test_incomplete_upstream_page_is_an_error_not_an_empty_report(self):
        self.query.return_value = {'count': 2, 'results': []}
        self.assertEqual(self.post().status_code, 502)


if __name__ == "__main__":
    unittest.main()
