import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daily_social_post as daily
import reader_stories as stories


class ReaderStoriesTrial(unittest.TestCase):
    def test_calendar_and_pinterest(self):
        folder = Path(daily.__file__).parent
        plan = json.loads((folder / "reader_stories_trial.json").read_text())
        first = date(2026, 11, 20)
        self.assertEqual(
            set(plan), {(first + timedelta(days=i)).isoformat() for i in range(14)}
        )
        pins = [
            p
            for p in json.loads((folder / "scheduled_pins.json").read_text())
            if p["id"].startswith("reader-stories-14d-")
        ]
        self.assertEqual(len(pins), 4)
        for week in (0, 1):
            start = first + timedelta(days=7 * week)
            self.assertEqual(
                sum(
                    start
                    <= date.fromisoformat(p["publish_at"][:10])
                    < start + timedelta(days=7)
                    for p in pins
                ),
                2,
            )
        for pin in pins:
            self.assertTrue(
                (folder.parents[1] / "assets" / "pins" / pin["image"]).is_file()
            )
            self.assertIn("utm_campaign=reader_stories_14d", pin["link"])
        for day, item in plan.items():
            p = {
                "slug": item["slug"],
                "title": "Test",
                "trial": item,
                "trial_date": day,
            }
            fb, ig = stories.captions(stories.edition(p), p, "https://example.test")
            self.assertIn("utm_content=" + day, fb)
            self.assertNotIn("https://example.test", ig)
        self.assertNotEqual(
            stories.palette({}), stories.palette({"trial": plan["2026-11-27"]})
        )

    def test_partial_publish_retry_and_expiry(self):
        # Exercise the scheduled entry point without external calls or credentials.
        args = SimpleNamespace(
            at_hour=11,
            slug=None,
            content=None,
            dry_run=False,
            preview_date=None,
            editorial=False,
            pin_preview=None,
            facebook_only=False,
            out=None,
        )
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            ledger = Path(tmp) / "posts.json"
            stack.enter_context(patch.object(daily, "STATE", ledger))
            now = stack.enter_context(
                patch.object(daily, "datetime", wraps=daily.datetime)
            )
            now.now.return_value = daily.datetime.fromisoformat(
                "2026-11-20T11:03:00-05:00"
            )

            def pick(client, state, slug):
                return {
                    "slug": slug or "regular-product",
                    "id": 1,
                    "title": "Test",
                    "price_usd": 5,
                }

            stack.enter_context(patch.object(daily, "pick_product", side_effect=pick))
            stack.enter_context(patch.object(daily, "product_images", return_value=[]))
            stack.enter_context(patch.object(daily.httpx, "Client"))
            stack.enter_context(
                patch.object(
                    daily, "render", side_effect=lambda p, i, out, seed: out.touch()
                )
            )
            stack.enter_context(
                patch.object(
                    stories, "render", side_effect=lambda s, p, i, out: out.touch()
                )
            )
            api = MagicMock()
            api.facebook.return_value = "fb-id"
            api.instagram.side_effect = [RuntimeError("mock"), "ig-id", "regular-ig-id"]
            stack.enter_context(patch.object(daily, "Meta", return_value=api))
            pin = stack.enter_context(patch.object(daily, "pinterest_round"))
            with self.assertRaises(SystemExit):
                daily.run(SimpleNamespace(**vars(args)))
            daily.run(SimpleNamespace(**vars(args)))
            daily.run(SimpleNamespace(**vars(args)))
            (entry,) = json.loads(ledger.read_text())
            self.assertTrue(entry["ok"])
            self.assertEqual(entry["slug"], "wooden-finger-book-holder")
            self.assertEqual(api.facebook.call_count, 1)
            self.assertEqual(api.instagram.call_count, 2)
            pin.assert_not_called()
            now.now.return_value = daily.datetime.fromisoformat(
                "2026-12-04T11:03:00-05:00"
            )
            pin.return_value = {}
            daily.run(SimpleNamespace(**vars(args)))
            self.assertEqual(
                json.loads(ledger.read_text())[-1]["slug"], "regular-product"
            )
            pin.assert_called_once()
