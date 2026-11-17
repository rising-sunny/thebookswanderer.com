"""The quiz campaign script only builds calls the owner's gate accepts: PAUSED objects under the budget cap."""
import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services import supplier_api

spec = importlib.util.spec_from_file_location("meta_create_quiz_campaign", ROOT / "scripts" / "meta_create_quiz_campaign.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

ARGS = dict(account="act_123", page="456", pixel="789", countries=["US", "GB"], budget=700, start="2026-11-26", end="2026-12-09")


class MetaQuizCampaignTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"TBW_META_ADS_MAX_DAILY_BUDGET": "2000", "TBW_SUPPLIER_ORDERS_ENABLED": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_every_call_passes_the_gate(self):
        steps = script.build(**ARGS)
        self.assertEqual([label for label, _, _ in steps],
                         ["campaign", "ad set", "creative a", "creative b", "ad a", "ad b"])
        for label, path, body in steps:
            supplier_api.check("meta", "POST", path, body)

    def test_campaign_set_and_ads_are_created_paused(self):
        for label, _, body in script.build(**ARGS):
            if label in ("campaign", "ad set") or label.startswith("ad "):
                self.assertEqual(body["status"], "PAUSED", label)

    def test_a_budget_over_the_cap_is_refused_by_the_gate(self):
        steps = script.build(**{**ARGS, "budget": 2500})
        with self.assertRaises(PermissionError):
            supplier_api.check("meta", "POST", steps[0][1], steps[0][2])

    def test_the_lead_event_is_optimised_on_the_given_pixel_and_the_page_is_ours(self):
        steps = dict((label, body) for label, _, body in script.build(**ARGS))
        self.assertEqual(steps["ad set"]["promoted_object"], {"pixel_id": "789", "custom_event_type": "LEAD"})
        self.assertEqual(steps["ad set"]["targeting"]["geo_locations"]["countries"], ["US", "GB"])
        for key in ("creative a", "creative b"):
            story = steps[key]["object_story_spec"]
            self.assertEqual(story["page_id"], "456")
            self.assertIn("utm_source=meta", story["link_data"]["link"])
            self.assertTrue(story["link_data"]["link"].startswith("https://thebookswanderer.com/guides/what-kind-of-reader-are-you/"))

    def test_the_ad_images_exist_in_the_repository(self):
        for ad in script.ADS.values():
            self.assertTrue((ROOT.parent / "assets" / "ads" / ad["image"]).is_file(), ad["image"])

    def test_dry_run_prints_and_sends_nothing(self):
        out = io.StringIO()
        with patch.object(sys, "argv", ["meta_create_quiz_campaign.py"]), redirect_stdout(out), \
                patch.object(supplier_api, "call", side_effect=AssertionError("must not call Meta")):
            self.assertEqual(script.main(), 0)
        self.assertIn("Dry run: nothing was sent", out.getvalue())


if __name__ == "__main__":
    unittest.main()
