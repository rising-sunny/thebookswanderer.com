import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from PIL import Image

spec = importlib.util.spec_from_file_location(
    "static_social_post", Path(__file__).parents[1] / "scripts/static_social_post.py")
social = importlib.util.module_from_spec(spec)
spec.loader.exec_module(social)


class PhotoPostTests(unittest.TestCase):
    def run_flow(self, failure=None):
        calls = []

        def handle(request):
            calls.append((request.method, request.url.path, request.content))
            path = request.url.path
            if request.method == "POST" and failure == path:
                raise httpx.ReadTimeout("hidden", request=request)
            responses = {
                "/v21.0/" + social.PAGE: {"id": social.PAGE,
                    "instagram_business_account": {"id": social.INSTAGRAM}},
                "/v21.0/" + social.INSTAGRAM: {"username": "thebooks.wanderer"},
                "/v21.0/" + social.PAGE + "/photos": {"id": "photo", "post_id": "post"},
                "/v21.0/" + social.INSTAGRAM + "/media": {"id": "container"},
                "/v21.0/container": {"status_code": "FINISHED"},
                "/v21.0/" + social.INSTAGRAM + "/media_publish": {"id": "media"},
                "/v21.0/media": {"permalink": "https://instagram.com/p/example/", "media_type": "IMAGE"},
            }
            return httpx.Response(200, json=responses[path])

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.json"
            journal = {"facebook": {"state": "ready"}, "instagram": {"state": "ready"}}
            payload = {"image_url": social.STORE + "/photo.jpg"}
            with httpx.Client(transport=httpx.MockTransport(handle)) as client:
                if failure:
                    with self.assertRaises(httpx.ReadTimeout):
                        social.publish(client, "private", payload, path, journal)
                    journal = json.loads(path.read_text())
                    count = len(calls)
                    with self.assertRaises(social.SafeError):
                        social.publish(client, "private", payload, path, journal)
                    self.assertEqual(count, len(calls))
                else:
                    social.publish(client, "private", payload, path, journal)
                    social.publish(client, "private", payload, path, journal)
                    self.assertEqual(journal["instagram"]["media_type"], "IMAGE")
            return calls

    def test_success_and_retry_publish_only_one_photo_per_network(self):
        writes = [call for call in self.run_flow() if call[0] == "POST"]
        self.assertEqual(len(writes), 3)
        self.assertFalse(any(b"REELS" in call[2] or "video" in call[1] for call in writes))

    def test_uncertain_facebook_write_blocks_retry(self):
        self.run_flow("/v21.0/" + social.PAGE + "/photos")

    def test_uncertain_instagram_publish_does_not_repeat_facebook(self):
        self.run_flow("/v21.0/" + social.INSTAGRAM + "/media_publish")

    def test_preflight_checks_jpeg_without_sending_credentials(self):
        output = io.BytesIO()
        Image.new("RGB", (1024, 1024)).save(output, "JPEG")

        def handle(request):
            self.assertNotIn("authorization", request.headers)
            if request.url.path.startswith("/api/"):
                return httpx.Response(200, json={"name": "The Reading Society Tote",
                                                "image_url": "/photo.jpg"})
            return httpx.Response(200, content=output.getvalue())

        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            self.assertEqual(social.preflight(client)["image_url"], social.STORE + "/photo.jpg")

    def test_foreign_or_credential_bearing_image_url_is_rejected(self):
        for url in ("https://example.com/a.jpg", "https://private@thebookswanderer.com/a.jpg",
                    "http://thebookswanderer.com/a.jpg", "/a.jpg?token=private"):
            with self.subTest(url=url), self.assertRaises(social.SafeError):
                social.owned_url(url)


if __name__ == "__main__":
    unittest.main()
