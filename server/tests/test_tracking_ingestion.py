"""Public ingestion tests against an in-memory database; all geo lookup is mocked."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from database import Base
from models import LiveEvent
import live


class TrackingIngestionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def send(self, kind):
        body = json.dumps(dict(type=kind, session_id="fixture-browser", path="/fixture",
                               value=999, extra={"order_id":1})).encode()
        async def receive():
            return dict(type="http.request", body=body, more_body=False)
        request = Request(dict(type="http", method="POST", path="/api/track",
                               headers=[(b"user-agent", b"Fixture")]), receive)
        with patch.object(live, "_is_ignored", return_value=False), \
             patch.object(live, "_classify_ua", return_value="desktop"), \
             patch.object(live.geo, "extract_client_ip", return_value=""), \
             patch.object(live.geo, "lookup", return_value={}), \
             patch.object(live, "_meta_bot", return_value=None):
            return asyncio.run(live.track(request, self.db))

    def test_cached_purchase_is_return_and_cannot_confirm_payment(self):
        self.assertEqual(self.send("purchase"), {"ok":True})
        self.assertEqual(self.db.query(LiveEvent).one().event_type, "purchase_return")
        self.assertEqual(live._build_snapshot(self.db)["today"]["purchases"], 0)
        self.assertEqual(live._build_snapshot(self.db)["today"]["revenue"], 0)

    def test_challenge_events_and_returns_are_accepted(self):
        for kind in ("challenge_request", "challenge_product_click", "purchase_return"):
            self.assertEqual(self.send(kind), {"ok":True})
        self.assertEqual(self.db.query(LiveEvent).count(), 3)

    def test_unknown_event_does_not_write(self):
        self.assertEqual(self.send("fixture_unknown").status_code, 400)
        self.assertEqual(self.db.query(LiveEvent).count(), 0)

if __name__ == '__main__':
    unittest.main()
