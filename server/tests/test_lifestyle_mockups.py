"""Protect existing catalog data when appending reviewed lifestyle images."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_lifestyle_mockups as script
from database import Base
from models import Product
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class LifestyleMockupsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "assets/products/example/ambient.jpg"
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"reviewed-asset")
        self.spec = {"slug": "example", "images": [{"url": "/assets/products/example/ambient.jpg", "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest()}]}
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.product = Product(slug="example", title="Original title", description="Keep description", image_url="/original.jpg", gallery_json=json.dumps(["/back.jpg", "/interior.jpg"]), price_usd=12.99, active=True)
        self.db.add(self.product)
        self.db.commit()

    def test_preserves_originals_and_other_fields_and_is_repeatable(self):
        changes = script.prepare(self.db, Product, [self.spec], self.root)
        script.apply_changes(self.db, Product, changes)
        self.assertEqual(json.loads(self.product.gallery_json), [self.spec["images"][0]["url"], "/back.jpg", "/interior.jpg"])
        self.assertEqual((self.product.title, self.product.description, self.product.price_usd, self.product.image_url), ("Original title", "Keep description", 12.99, "/original.jpg"))
        self.assertEqual(script.prepare(self.db, Product, [self.spec], self.root), [])

    def test_missing_product_aborts_before_any_gallery_change(self):
        other = {**self.spec, "slug": "missing"}
        original = self.product.gallery_json
        with self.assertRaises(ValueError):
            script.prepare(self.db, Product, [self.spec, other], self.root)
        self.assertEqual(self.product.gallery_json, original)

    def test_changed_asset_is_rejected(self):
        self.path.write_bytes(b"unreviewed replacement")
        with self.assertRaisesRegex(ValueError, "checksum"):
            script.prepare(self.db, Product, [self.spec], self.root)

    def test_concurrent_gallery_change_is_not_overwritten(self):
        changes = script.prepare(self.db, Product, [self.spec], self.root)
        self.product.gallery_json = '["/new-user-photo.jpg"]'
        self.db.commit()
        with self.assertRaises(ValueError):
            script.apply_changes(self.db, Product, changes)
        self.assertEqual(self.product.gallery_json, '["/new-user-photo.jpg"]')

    def test_published_manifest_assets_exist_and_match(self):
        manifest = json.loads((Path(script.__file__).parent / "lifestyle_mockups_20261020.json").read_text())
        for spec in manifest["products"]:
            with self.subTest(slug=spec["slug"]):
                self.assertTrue(script.image_urls(spec, script.ROOT))


if __name__ == "__main__":
    unittest.main()
