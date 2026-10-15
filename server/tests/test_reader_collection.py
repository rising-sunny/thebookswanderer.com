"""Offline publication and paid-fulfillment mapping checks (no supplier orders)."""
import asyncio
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import publish_reader_collection as release
from database import Base
from models import Product, ProductVariant
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        _, self.book, self.tote = release.read_spec()
        self.files = {'interior': 'private-interior.pdf', 'cover': 'private-cover.pdf'}
        self.info = {'cost_usd': 9.67, 'variant_id': 101409}

    def test_print_mappings_and_idempotent_publication_preserve_other_products(self):
        unrelated = Product(slug='existing', title='Existing', supplier='cj', price_usd=12)
        self.db.add(unrelated)
        for _ in range(2):
            book = release.apply_product(self.db, self.book, files=self.files)
            tote = release.apply_product(self.db, self.tote, tote=self.info)
            self.db.commit()
        self.assertEqual(self.db.query(Product).count(), 3)
        self.assertEqual(self.db.query(ProductVariant).count(), 2)
        self.assertEqual(unrelated.price_usd, 12)
        self.assertEqual(book.price_usd, 24.99)
        self.assertEqual(book.lulu_package, '0583X0827BWSTDPB060UW444MXX')
        bv = book.default_variant()
        self.assertEqual((bv.digital_file, bv.print_cover), tuple(self.files.values()))
        self.assertEqual(bv.cj_vid, 'lulu-book-club-companion-en')
        self.assertEqual(bv.printify_variant_id, 0)
        self.assertEqual(tote.printify_product_id, self.tote['printify_id'])
        self.assertEqual((tote.from_country, tote.price_usd), ('US', 27.99))
        tv = tote.default_variant()
        self.assertEqual(tv.printify_variant_id, 101409)
        self.assertEqual((tv.cj_vid, tv.digital_file, tv.print_cover), ('', '', ''))

    def test_existing_slug_from_different_supplier_is_rejected(self):
        self.db.add(Product(slug=self.book['slug'], title='Do not replace', supplier='cj'))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'different supplier'):
            release.apply_product(self.db, self.book, files=self.files)

    def test_replaced_variant_is_deactivated_without_deleting_history(self):
        product = release.apply_product(self.db, self.tote, tote=self.info)
        self.db.commit()
        old = ProductVariant(product=product, name='Retired', price_usd=25, active=True)
        self.db.add(old)
        self.db.commit()
        release.apply_product(self.db, self.tote, tote=self.info)
        self.db.commit()
        self.assertFalse(old.active)
        self.assertEqual(len(product.active_variants()), 1)
        self.assertEqual(self.db.query(ProductVariant).count(), 2)


class SupplierGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _, _, self.tote = release.read_spec()
        self.product = {'id': self.tote['printify_id'], 'blueprint_id': 1313, 'print_provider_id': 99,
                        'variants': [{'id': 101409, 'is_enabled': True, 'is_available': True, 'cost': 967}],
                        'print_areas': [{'variant_ids': [101409], 'placeholders': [
                            {'position': 'front', 'images': [{'id': self.tote['artwork_upload_id']}]}]}]}

    async def test_unavailable_variant_blocks_release_before_shipping_call(self):
        self.product['variants'][0]['is_available'] = False
        with patch.object(release.printify, '_request', AsyncMock(return_value=self.product)), \
                patch.object(release.printify, 'shipping_cost', AsyncMock()) as shipping:
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                await release.tote_info(self.tote)
            shipping.assert_not_awaited()

    async def test_wrong_original_artwork_is_rejected(self):
        self.product['print_areas'][0]['placeholders'][0]['images'][0]['id'] = 'wrong-art'
        with patch.object(release.printify, '_request', AsyncMock(return_value=self.product)):
            with self.assertRaisesRegex(ValueError, 'artwork'):
                await release.tote_info(self.tote)

    async def test_cost_increase_blocks_publication(self):
        with patch.object(release.printify, '_request', AsyncMock(return_value=self.product)), \
                patch.object(release.printify, 'shipping_cost', AsyncMock(return_value=8)):
            with self.assertRaisesRegex(ValueError, 'cost limit'):
                await release.tote_info(self.tote)


if __name__ == '__main__':
    unittest.main()
