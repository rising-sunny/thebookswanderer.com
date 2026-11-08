"""Pinterest wipe: only the right account, deletes and cleans the local record, remembers refusals."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from scripts import pinterest_wipe


class Boom(Exception):
    def __init__(self, code):
        self.status_code = code


class FakePinterest:
    def __init__(self, ids, username="TheBooksWanderer", refuse=(), gone=(), rate_after=None):
        self.ids = list(ids)
        self.username, self.refuse, self.gone, self.rate_after = username, set(refuse), set(gone), rate_after
        self.deleted, self.calls = [], 0

    async def __call__(self, method, path, **kw):
        self.calls += 1
        if path == "/user_account":
            return {"username": self.username, "pin_count": len(self.ids)}
        if method == "GET":
            assert "include_protected_pins=true" in path
            items = [{"id": i} for i in self.ids]
            start = 0
            if "bookmark=" in path:
                start = int(path.split("bookmark=")[1])
            page = items[start:start + pinterest_wipe.PAGE]
            nxt = start + pinterest_wipe.PAGE
            return {"items": page, "bookmark": str(nxt) if nxt < len(items) else None}
        pin = path.rsplit("/", 1)[1]
        if self.rate_after is not None and len(self.deleted) >= self.rate_after:
            raise Boom(429)
        if pin in self.gone:
            raise Boom(404)
        if pin in self.refuse:
            raise Boom(400)
        self.deleted.append(pin)
        self.ids.remove(pin)
        return {}


async def nap(_):
    return None


class Wipe(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        models.PinterestPin.__table__.create(engine)
        self.db = sessionmaker(bind=engine)()
        self.addCleanup(self.db.close)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.refused = Path(directory.name) / "refused.json"

    def rows(self, ids):
        for i in ids:
            self.db.add(models.PinterestPin(pin_id=i, product_slug="x"))
        self.db.commit()

    def run_wipe(self, api, **kw):
        args = dict(apply=True, limit=1000, budget=60, delay=0, refused_file=self.refused, pause=nap)
        args.update(kw)
        return asyncio.run(pinterest_wipe.wipe(api, self.db, **args))

    def test_dry_run_deletes_nothing(self):
        api = FakePinterest(["1", "2"])
        out = self.run_wipe(api, apply=False)
        self.assertEqual(out["first_page_deletable"], 2)
        self.assertEqual(api.deleted, [])

    def test_other_account_is_never_touched(self):
        api = FakePinterest(["1"], username="MathRelaxing")
        out = self.run_wipe(api)
        self.assertIn("aborted", out)
        self.assertEqual(api.deleted, [])

    def test_deletes_everything_and_resets_the_local_record(self):
        ids = [str(n) for n in range(250)]
        self.rows(ids + ["old-not-on-pinterest"])
        api = FakePinterest(ids)
        out = self.run_wipe(api)
        self.assertEqual(out["deleted"], 250)
        self.assertTrue(out["listing_finished"])
        self.assertTrue(out["local_record_reset"])
        self.assertEqual(self.db.query(models.PinterestPin).count(), 0)

    def test_batch_limit_stops_and_keeps_the_rest(self):
        ids = [str(n) for n in range(30)]
        self.rows(ids)
        api = FakePinterest(ids)
        out = self.run_wipe(api, limit=10)
        self.assertEqual(out["deleted"], 10)
        self.assertIn("limit", out["stopped"])
        self.assertEqual(self.db.query(models.PinterestPin).count(), 20)
        self.assertNotIn("local_record_reset", out)

    def test_refused_and_missing_pins(self):
        api = FakePinterest(["1", "2", "3"], refuse=["2"], gone=["3"])
        self.rows(["1", "2", "3"])
        out = self.run_wipe(api)
        self.assertEqual((out["deleted"], out["refused"], out["gone"]), (1, 1, 1))
        self.assertNotIn("local_record_reset", out)
        self.assertIn('"2"', self.refused.read_text())
        # next batch skips the refused pin instead of retrying it forever
        api.calls = 0
        out2 = self.run_wipe(api)
        self.assertEqual((out2["deleted"], out2["refused"]), (0, 0))

    def test_rate_limit_stops_the_batch(self):
        api = FakePinterest([str(n) for n in range(10)], rate_after=3)
        out = self.run_wipe(api)
        self.assertEqual(out["deleted"], 3)
        self.assertIn("rate limit", out["stopped"])

    def test_gives_up_when_pinterest_refuses_every_delete(self):
        ids = [str(n) for n in range(60)]
        api = FakePinterest(ids, refuse=ids)
        out = self.run_wipe(api)
        self.assertEqual(out["deleted"], 0)
        self.assertEqual(out["refused"], 25)
        self.assertIn("refuses", out["stopped"])


if __name__ == "__main__":
    unittest.main()
