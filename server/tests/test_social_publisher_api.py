import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location(
    "publisher_api", Path(__file__).parents[1] / "scripts/social_publisher_api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class PublisherApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        directory = Path(self.tmp.name)
        self.root = patch.object(api, "ROOT", directory)
        self.data = patch.object(api, "DATA", directory)
        key = directory / "key"
        key.write_text("x" * 40)
        (directory / ".env").write_text("FB_PAGE_TOKEN=test-only\nFB_PAGE_ID=1200587819810293\n")
        self.key = patch.object(api, "KEY", key)
        for item in (self.root, self.data, self.key):
            item.start()
            self.addCleanup(item.stop)
        self.headers = {"Authorization": "Bearer " + "x" * 40}
        self.client = TestClient(api.app)
        self.body = {"campaign": "test_photo_001", "slug": "reading-society-tote",
                     "facebook_caption": "Caption FB", "instagram_caption": "Caption IG"}

    def draft(self):
        with patch.object(api, "image_preflight", return_value={"image_url": "https://thebookswanderer.com/a.jpg"}):
            return self.client.post("/drafts", headers=self.headers, json=self.body)

    def test_unauthenticated_requests_cannot_read_or_write(self):
        self.assertEqual(self.client.get("/health").status_code, 401)
        self.assertEqual(self.client.post("/drafts", json=self.body).status_code, 401)

    def test_health_is_read_only_and_does_not_expose_credentials(self):
        with patch.object(api.httpx.HTTPTransport, "handle_request", side_effect=AssertionError("No network")):
            result = self.client.get("/health", headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("test-only", result.text)

    def test_existing_reference_cannot_change_caption(self):
        self.assertEqual(self.draft().status_code, 200)
        self.body["facebook_caption"] = "Changed"
        self.assertEqual(self.draft().status_code, 409)

    def test_repeated_publish_submits_only_once(self):
        self.draft()
        with patch.object(api, "run_job") as runner:
            for _ in range(2):
                self.client.post("/jobs/test_photo_001/publish", headers=self.headers)
            self.assertEqual(runner.call_count, 1)

    def test_invalid_refs_and_unknown_fields_are_rejected(self):
        self.body["campaign"] = "../escape"
        self.assertEqual(self.draft().status_code, 422)
        self.body["campaign"] = "valid_ref"
        self.body["token"] = "unwanted"
        self.assertEqual(self.draft().status_code, 422)

    def test_restart_does_not_resend_interrupted_job(self):
        self.draft()
        path = api.journal_path("test_photo_001")
        record = json.loads(path.read_text())
        record["job"] = "publishing"
        api.core().save(path, record)
        api.reconcile_interrupted_jobs()
        with patch.object(api, "run_job") as runner:
            self.client.post("/jobs/test_photo_001/publish", headers=self.headers)
            runner.assert_not_called()
        self.assertEqual(json.loads(path.read_text())["job"], "review_required")

    def test_worker_uses_the_saved_captions_and_records_success(self):
        self.draft()
        module = api.core()
        def publish(client, token, payload, path, journal):
            self.assertEqual(module.FB_TEXT, "Caption FB")
            self.assertEqual(module.IG_TEXT, "Caption IG")
            journal["facebook"]["state"] = "published"
            journal["instagram"]["state"] = "published"
        with patch.object(api, "core", return_value=module), \
             patch.object(api, "image_preflight", return_value={"image_url": "https://thebookswanderer.com/a.jpg"}), \
             patch.object(module, "publish", side_effect=publish):
            api.run_job("test_photo_001")
        record = json.loads(api.journal_path("test_photo_001").read_text())
        self.assertEqual(record["job"], "published")

    def test_worker_failure_keeps_uncertain_state_for_review(self):
        self.draft()
        module = api.core()
        def interrupted(client, token, payload, path, journal):
            journal["facebook"]["state"] = "uncertain"
            module.save(path, journal)
            raise TimeoutError("hidden")
        with patch.object(api, "core", return_value=module), \
             patch.object(api, "image_preflight", return_value={"image_url": "https://thebookswanderer.com/a.jpg"}), \
             patch.object(module, "publish", side_effect=interrupted):
            api.run_job("test_photo_001")
        record = json.loads(api.journal_path("test_photo_001").read_text())
        self.assertEqual(record["job"], "review_required")
        self.assertEqual(record["facebook"]["state"], "uncertain")


if __name__ == "__main__":
    unittest.main()
