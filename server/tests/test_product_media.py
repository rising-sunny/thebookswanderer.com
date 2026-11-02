"""Offline product gallery persistence and authenticated upload tests."""
import io
import json
import os
import re
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import Base, get_db
from live import ADMIN_COOKIE, _make_cookie
from models import Product, ProductVariant
from routers.product_media import router
from services import product_media as media


def picture(color="red", format="PNG"):
    out = io.BytesIO()
    Image.new("RGB", (200, 200), color).save(out, format=format)
    return out.getvalue()


class ProductMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {
            "LIVE_ADMIN_PASSWORD": "fake-owner-password", "LIVE_ADMIN_USER": "owner",
            "TBW_PRODUCT_MEDIA_DIR": str(self.root / "public"),
            "TBW_PRODUCT_MEDIA_PRIVATE_DIR": str(self.root / "private"),
        })
        self.env.start()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            p = Product(id=73, slug="miniature-library", title="Mini <Library>",
                        image_url="https://example.test/real.jpg",
                        gallery_json=json.dumps(["https://example.test/real.jpg", "https://example.test/detail.jpg"]),
                        active=True, draft=False, price_usd=44.99)
            p.variants = [ProductVariant(name="Complete", active=True, price_usd=44.99)]
            db.add(p)
            db.add(Product(id=74, slug="other", title="Other", gallery_json="[]", active=False, draft=True))
            db.commit()
        self.app = FastAPI()
        self.app.include_router(router)

        def session():
            with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = session
        self.client = TestClient(self.app)
        self.client.cookies.set(ADMIN_COOKIE, _make_cookie("owner"))

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.env.stop()
        self.tmp.cleanup()

    def form(self):
        response = self.client.get("/admin/product-media/?product_id=73")
        self.assertEqual(response.status_code, 200)
        return {key: re.search(r'name="' + key + r'" value="([^"]+)"', response.text).group(1)
                for key in ("csrf", "revision", "product_id")}

    def upload(self, *, data=None, image=None, **kwargs):
        values = self.form() if data is None else data
        values.update(origin="ai", disclosed="true")
        values.update(kwargs)
        return self.client.post("/admin/product-media/append", data=values,
                                files={"files": ("untrusted-name.svg", image or picture(), "text/plain")},
                                follow_redirects=False)

    def test_requires_owner_login_and_rejects_future_cookie(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/admin/product-media/", follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.post("/admin/product-media/remove", data={"product_id": 73, "revision": "x", "url": "x"}).status_code, 401)
        with patch("live.time.time", return_value=9999999999):
            cookie = _make_cookie("owner")
        self.client.cookies.set(ADMIN_COOKIE, cookie)
        self.assertEqual(self.client.get("/admin/product-media/", follow_redirects=False).status_code, 303)

    def test_rejects_missing_or_other_session_csrf(self):
        values = self.form()
        values["csrf"] = "wrong"
        self.assertEqual(self.upload(data=values).status_code, 403)
        with self.sessions() as db:
            self.assertEqual(len(media.gallery(db.get(Product, 73))), 2)
        self.assertFalse((self.root / "public").exists())

    def test_append_preserves_bytes_hero_prices_and_publication_with_backup(self):
        data = picture()
        self.assertEqual(self.upload(image=data).status_code, 303)
        with self.sessions() as db:
            p = db.get(Product, 73)
            urls = media.gallery(p)
            self.assertEqual(urls[:2], ["https://example.test/real.jpg", "https://example.test/detail.jpg"])
            self.assertTrue(urls[-1].endswith(".png"))
            self.assertEqual(p.image_url, "https://example.test/real.jpg")
            self.assertTrue(p.active)
            self.assertFalse(p.draft)
            self.assertEqual(p.price_usd, 44.99)
            self.assertEqual(p.variants[0].price_usd, 44.99)
            self.assertEqual(media.gallery(db.get(Product, 74)), [])
        saved = next((self.root / "public/73").glob("*.png"))
        self.assertEqual(saved.read_bytes(), data)
        backups = list((self.root / "private").glob("*.json"))
        self.assertEqual(len(backups), 1)
        backup = json.loads(backups[0].read_text())
        self.assertEqual(backup["origin"], "ai")
        self.assertEqual(len(json.loads(backup["before_gallery_json"])), 2)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_upload_repeated_is_idempotent(self):
        self.assertEqual(self.upload().status_code, 303)
        self.assertEqual(self.upload().status_code, 303)
        with self.sessions() as db:
            self.assertEqual(len(media.gallery(db.get(Product, 73))), 3)
        self.assertEqual(len(list((self.root / "private").glob("*.json"))), 1)

    def test_ai_upload_requires_embedded_disclosure_confirmation(self):
        self.assertEqual(self.upload(disclosed="false").status_code, 400)
        self.assertFalse((self.root / "public").exists())

    def test_real_upload_does_not_require_ai_confirmation(self):
        self.assertEqual(self.upload(origin="real", disclosed="false").status_code, 303)

    def test_stale_form_does_not_replace_newer_gallery(self):
        stale = self.form()
        self.assertEqual(self.upload().status_code, 303)
        self.assertEqual(self.upload(data=stale, image=picture("blue")).status_code, 400)
        with self.sessions() as db:
            self.assertEqual(len(media.gallery(db.get(Product, 73))), 3)

    def test_invalid_svg_truncated_and_oversize_images_are_refused(self):
        for data in (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", picture()[:40], b"a" * (media.MAX_BYTES + 1)):
            with self.subTest(size=len(data)):
                self.assertEqual(self.upload(image=data).status_code, 400)
        self.assertFalse((self.root / "public").exists())

    def test_invalid_batch_does_not_save_any_image(self):
        values = self.form() | {"origin": "real"}
        response = self.client.post("/admin/product-media/append", data=values,
            files=[("files", ("real.png", picture(), "image/png")),
                   ("files", ("bad.png", b"invalid", "image/png"))])
        self.assertEqual(response.status_code, 400)
        self.assertFalse((self.root / "public").exists())

    def test_rejects_too_many_files_and_full_gallery(self):
        with self.sessions() as db:
            p = db.get(Product, 73)
            with self.assertRaises(media.MediaError):
                media.append(db, p, media.revision(p), [picture()] * 4, origin="real", disclosed=False)
            p.gallery_json = json.dumps([p.image_url, *[f"https://example.test/{n}.jpg" for n in range(23)]])
            db.commit()
        self.assertEqual(self.upload().status_code, 400)
        self.assertFalse((self.root / "public").exists())

    def test_only_additional_local_images_can_be_removed_without_deleting_bytes(self):
        self.upload()
        with self.sessions() as db:
            url = media.gallery(db.get(Product, 73))[-1]
        values = self.form() | {"url": url}
        response = self.client.post("/admin/product-media/remove", data=values, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertTrue(list((self.root / "public/73").glob("*.png")))
        with self.sessions() as db:
            self.assertEqual(len(media.gallery(db.get(Product, 73))), 2)
        for forbidden in ("https://example.test/real.jpg", url.replace("/73/", "/74/"), "/etc/passwd"):
            self.assertEqual(self.client.post("/admin/product-media/remove", data=self.form() | {"url": forbidden}).status_code, 400)

    def test_failed_backup_leaves_gallery_unchanged(self):
        with patch.object(media, "_private_json", side_effect=OSError("no disk")):
            self.assertEqual(self.upload().status_code, 503)
        with self.sessions() as db:
            self.assertEqual(len(media.gallery(db.get(Product, 73))), 2)

    def test_jpeg_webp_and_huge_dimensions(self):
        self.assertEqual(media.validate_image(picture(format="JPEG")), "jpg")
        self.assertEqual(media.validate_image(picture(format="WEBP")), "webp")
        out = io.BytesIO()
        Image.new("1", (5000, 5000)).save(out, format="PNG")
        with self.assertRaises(media.MediaError):
            media.validate_image(out.getvalue())

    def test_admin_preview_escapes_title_and_is_private(self):
        page = self.client.get("/admin/product-media/?product_id=73")
        self.assertIn("Mini &lt;Library&gt;", page.text)
        self.assertIn("no-store", page.headers["cache-control"])
        self.assertIn("noindex", page.headers["x-robots-tag"])

    def test_compare_and_set_refuses_a_concurrent_edit(self):
        with self.sessions() as stale, self.sessions() as other:
            product = stale.get(Product, 73)
            revision = media.revision(product)
            current = other.get(Product, 73)
            current.gallery_json = json.dumps([current.image_url, "https://example.test/new.jpg"])
            other.commit()
            with self.assertRaises(media.MediaError):
                media.append(stale, product, revision, [picture()], origin="real", disclosed=False)
        with self.sessions() as db:
            self.assertEqual(media.gallery(db.get(Product, 73))[-1], "https://example.test/new.jpg")

    def test_bundle_installer_checks_identity_hashes_and_is_repeatable(self):
        path = Path(__file__).resolve().parents[1] / "scripts/install_mini_library_ai_images.py"
        spec = importlib.util.spec_from_file_location("gallery_bundle", path)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        folder = self.root / "bundle"
        folder.mkdir()
        import hashlib
        manifest = []
        for name, color in [("reading-desk.webp", "red"), ("reading-nook.webp", "green"), ("detail.webp", "blue")]:
            data = picture(color, "WEBP")
            (folder / name).write_bytes(data)
            manifest.append({"file": name, "sha256": hashlib.sha256(data).hexdigest(),
                             "ai_generated": True, "embedded_disclosure": True})
        (folder / "manifest.json").write_text(json.dumps(manifest))
        with self.sessions() as db:
            # Matching an ID alone is insufficient to change a product.
            with self.assertRaises(SystemExit):
                installer.install(db, apply=True, asset_dir=folder)
            p = db.get(Product, 73)
            p.cj_pid = "2501150522201605300"
            db.commit()
            installer.install(db, asset_dir=folder)
            self.assertEqual(len(media.gallery(p)), 2)
            installer.install(db, apply=True, asset_dir=folder)
            installer.install(db, apply=True, asset_dir=folder)
            self.assertEqual(len(media.gallery(p)), 5)
            (folder / "detail.webp").write_bytes(b"tampered")
            with self.assertRaises(SystemExit):
                installer.install(db, apply=True, asset_dir=folder)
            self.assertEqual(len(media.gallery(p)), 5)


if __name__ == "__main__":
    unittest.main()
