"""Offline checks for the exact USB reading light publication and fulfillment mapping."""
import copy
import sys
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import publish_usb_reading_light as light
from database import Base
from models import Product, ProductVariant
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class LightVariantTests(unittest.TestCase):
    def setUp(self):
        self.details = {'pid': light.PID, 'productSku': 'CJJT1666548', 'variants': [
            {'vid': 'wrong-multipack', 'variantKey': 'Black-USB-3PCS', 'variantSellPrice': 9.20},
            {'vid': light.VID, 'variantKey': 'Black-USB-1PC', 'variantSku': light.SKU, 'variantSellPrice': 3.35}]}

    def test_selects_one_black_light_instead_of_first_multipack(self):
        self.assertEqual(light.selected_variant(self.details)['vid'], light.VID)

    def test_changed_sku_and_cost_increase_block_preparation(self):
        for key, value in [('variantSku', 'OTHER'), ('variantSellPrice', 6)]:
            details = copy.deepcopy(self.details)
            details['variants'][1][key] = value
            with self.assertRaises(ValueError):
                light.selected_variant(details)


class LightPublicationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, autoflush=False)()
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)
        self.spec = {'slug': light.SLUG, 'pid': light.PID, 'vid': light.VID, 'sku': light.SKU,
                     'price_usd': 16.99, 'title': 'Japanese A5 Book Cover', 'description': 'One black light.',
                     'details_html': '', 'category': 'book-accessories', 'variant_name': 'Black · 1 USB light',
                     'image_url': '/assets/products/usb-clip-reading-light/main.jpg', 'gallery': []}

    def test_idempotent_draft_preserves_unrelated_products_and_exact_cj_reference(self):
        self.db.add(Product(slug='existing', title='Existing', price_usd=10, active=True))
        self.db.commit()
        for _ in range(2):
            p = light.stage_product(self.db, self.spec, 3.35)
            self.db.commit()
        self.assertFalse(p.active)
        self.assertEqual((p.cj_pid, p.cj_vid, p.cj_sku), (light.PID, light.VID, light.SKU))
        self.assertEqual((p.from_country, p.price_usd), ('CN', 16.99))
        self.assertEqual(len(p.active_variants()), 1)
        v = p.default_variant()
        self.assertEqual((v.cj_vid, v.cj_sku, v.price_usd), (light.VID, light.SKU, 16.99))
        self.assertEqual(self.db.query(ProductVariant).count(), 1)
        self.assertEqual(self.db.query(Product).count(), 2)
        self.assertTrue(self.db.query(Product).filter_by(slug='existing').one().active)

    def test_publish_activates_existing_draft_without_duplicate_or_new_variant_ids(self):
        p = light.stage_product(self.db, self.spec, 3.35)
        self.db.commit()
        product_id, variant_id = p.id, p.default_variant().id
        self.spec['description'] = 'Black USB reading light. One unit.'
        for _ in range(2):
            p = light.stage_product(self.db, self.spec, 3.35, publish=True)
            self.db.commit()
        self.assertTrue(p.active)
        self.assertEqual((p.id, p.default_variant().id), (product_id, variant_id))
        self.assertEqual(p.description, self.spec['description'])
        self.assertEqual(p.default_variant().cj_vid, light.VID)
        self.assertEqual(p.default_variant().price_usd, 16.99)
        self.assertEqual(self.db.query(Product).count(), 1)
        self.assertEqual(self.db.query(ProductVariant).count(), 1)

    def test_publish_rejects_a_different_light_variant_before_writing(self):
        self.spec['vid'] = 'unreviewed-variant'
        with self.assertRaises(ValueError):
            light.stage_product(self.db, self.spec, 3.35, publish=True)
        self.assertEqual(self.db.query(Product).count(), 0)

    def test_active_listing_is_not_hidden_on_draft_rerun(self):
        p = light.stage_product(self.db, self.spec, 3.35)
        p.active = True
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'active listing'):
            light.stage_product(self.db, self.spec, 3.35)
        self.assertTrue(p.active)

    def test_supplier_collision_and_duplicate_product_are_rejected(self):
        self.db.add(Product(slug='different', title='Already exists', cj_pid=light.PID))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'different store listing'):
            light.stage_product(self.db, self.spec, 3.35)
        self.db.rollback()
        self.db.add(Product(slug=light.SLUG, title='Other supplier', cj_pid='other', supplier='lulu'))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'another supplier'):
            light.stage_product(self.db, self.spec, 3.35)


class LightSupplierGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_stock_blocks_before_shipping_request(self):
        details = {'pid': light.PID, 'productSku': 'CJJT1666548', 'variants': [
            {'vid': light.VID, 'variantKey': 'Black-USB-1PC', 'variantSku': light.SKU, 'variantSellPrice': 3.35}]}
        with patch.object(light.cj, 'get_product_details', AsyncMock(return_value=details)), \
                patch.object(light.cj, '_request', AsyncMock(return_value=[{'countryCode': 'CN', 'totalInventoryNum': 0}])), \
                patch.object(light.cj, 'freight_calculate', AsyncMock()) as freight, \
                patch.object(light.asyncio, 'sleep', AsyncMock()):
            with self.assertRaisesRegex(ValueError, 'no stock'):
                await light.validate_supplier()
            freight.assert_not_awaited()

    async def test_costly_route_blocks_before_publication(self):
        details = {'pid': light.PID, 'productSku': 'CJJT1666548', 'variants': [
            {'vid': light.VID, 'variantKey': 'Black-USB-1PC', 'variantSku': light.SKU, 'variantSellPrice': 3.35}]}
        with patch.object(light.cj, 'get_product_details', AsyncMock(return_value=details)), \
                patch.object(light.cj, '_request', AsyncMock(return_value=[{'countryCode': 'CN', 'totalInventoryNum': 8}])), \
                patch.object(light.cj, 'freight_calculate', AsyncMock(return_value=[{'logisticPrice': 12}])), \
                patch.object(light.asyncio, 'sleep', AsyncMock()):
            with self.assertRaisesRegex(ValueError, 'shipping exceeds'):
                await light.validate_supplier()


if __name__ == '__main__':
    unittest.main()
