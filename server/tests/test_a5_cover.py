"""Offline checks for the exact A5 cover draft and fulfillment mapping."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_a5_cover as cover
from database import Base
from models import Product, ProductVariant
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class CoverVariantTests(unittest.TestCase):
    def setUp(self):
        self.details = {'pid': cover.PID, 'productSku': 'CJJJJTJT36003', 'variants': [
            {'vid': 'wrong-a6-notebook', 'variantKey': 'Navy Blue-A6 notebook', 'variantSellPrice': 2.97},
            {'vid': cover.VID, 'variantKey': 'Navy Blue-A5', 'variantSku': cover.SKU, 'variantSellPrice': 2.61}]}

    def test_selects_cover_only_a5_not_first_variant_or_notebook(self):
        self.assertEqual(cover.selected_variant(self.details)['vid'], cover.VID)

    def test_changed_sku_and_cost_increase_block_preparation(self):
        for key, value in [('variantSku', 'OTHER'), ('variantSellPrice', 4)]:
            details = copy.deepcopy(self.details)
            details['variants'][1][key] = value
            with self.assertRaises(ValueError):
                cover.selected_variant(details)


class CoverDraftTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False)()
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)
        self.spec = {'slug': cover.SLUG, 'pid': cover.PID, 'vid': cover.VID, 'sku': cover.SKU,
                     'price_usd': 19.99, 'title': 'Japanese A5 Book Cover', 'description': 'Cover only.',
                     'details_html': '', 'category': 'book-accessories', 'variant_name': 'Navy crane · A5 cover',
                     'image_url': '/assets/products/japanese-a5-book-cover/main.jpg', 'gallery': []}

    def test_idempotent_draft_preserves_unrelated_products_and_exact_cj_reference(self):
        self.db.add(Product(slug='existing', title='Existing', price_usd=10, active=True))
        self.db.commit()
        for _ in range(2):
            p = cover.stage_product(self.db, self.spec, 2.61)
            self.db.commit()
        self.assertFalse(p.active)
        self.assertEqual((p.cj_pid, p.cj_vid, p.cj_sku), (cover.PID, cover.VID, cover.SKU))
        self.assertEqual((p.from_country, p.price_usd), ('CN', 19.99))
        self.assertEqual(len(p.active_variants()), 1)
        v = p.default_variant()
        self.assertEqual((v.cj_vid, v.cj_sku, v.price_usd), (cover.VID, cover.SKU, 19.99))
        self.assertEqual(self.db.query(ProductVariant).count(), 1)
        self.assertEqual(self.db.query(Product).count(), 2)
        self.assertTrue(self.db.query(Product).filter_by(slug='existing').one().active)

    def test_active_listing_is_not_hidden_on_draft_rerun(self):
        p = cover.stage_product(self.db, self.spec, 2.61)
        p.active = True
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'active listing'):
            cover.stage_product(self.db, self.spec, 2.61)
        self.assertTrue(p.active)

    def test_supplier_collision_and_duplicate_product_are_rejected(self):
        self.db.add(Product(slug='different', title='Already exists', cj_pid=cover.PID))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'different store listing'):
            cover.stage_product(self.db, self.spec, 2.61)
        self.db.rollback()
        self.db.add(Product(slug=cover.SLUG, title='Other supplier', cj_pid='other', supplier='lulu'))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'another supplier'):
            cover.stage_product(self.db, self.spec, 2.61)


if __name__ == '__main__':
    unittest.main()
