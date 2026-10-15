"""Offline publication and paid-fulfillment mapping checks (no supplier orders)."""
import asyncio
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import publish_nature_notebooks as release
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
        _, self.book, self.notebook = release.read_spec()
        self.files = {'interior': 'private-interior.pdf', 'cover': 'private-cover.pdf'}
        self.info = {'cost_usd': 9.67, 'variant_id': 65223}

    def test_print_mappings_and_idempotent_publication_preserve_other_products(self):
        unrelated = Product(slug='existing', title='Existing', supplier='cj', price_usd=12)
        self.db.add(unrelated)
        for _ in range(2):
            book = release.apply_product(self.db, self.book, files=self.files)
            notebook = release.apply_product(self.db, self.notebook, notebook=self.info)
            self.db.commit()
        self.assertEqual(self.db.query(Product).count(), 3)
        self.assertEqual(self.db.query(ProductVariant).count(), 2)
        self.assertEqual(unrelated.price_usd, 12)
        self.assertEqual(book.price_usd, 24.99)
        self.assertEqual(book.lulu_package, '0583X0827BWSTDPB060UW444MXX')
        bv = book.default_variant()
        self.assertEqual((bv.digital_file, bv.print_cover), tuple(self.files.values()))
        self.assertEqual(bv.cj_vid, 'lulu-commonplace-book-en')
        self.assertEqual(bv.printify_variant_id, 0)
        self.assertEqual(notebook.printify_product_id, self.notebook['printify_id'])
        self.assertEqual((notebook.from_country, notebook.price_usd), ('US', 27.99))
        tv = notebook.default_variant()
        self.assertEqual(tv.printify_variant_id, 65223)
        self.assertEqual((tv.cj_vid, tv.digital_file, tv.print_cover), ('', '', ''))

    def test_existing_slug_from_different_supplier_is_rejected(self):
        self.db.add(Product(slug=self.book['slug'], title='Do not replace', supplier='cj'))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'different supplier'):
            release.apply_product(self.db, self.book, files=self.files)

    def test_replaced_variant_is_deactivated_without_deleting_history(self):
        product = release.apply_product(self.db, self.notebook, notebook=self.info)
        self.db.commit()
        old = ProductVariant(product=product, name='Retired', price_usd=25, active=True)
        self.db.add(old)
        self.db.commit()
        release.apply_product(self.db, self.notebook, notebook=self.info)
        self.db.commit()
        self.assertFalse(old.active)
        self.assertEqual(len(product.active_variants()), 1)
        self.assertEqual(self.db.query(ProductVariant).count(), 2)

    def test_supplier_product_cannot_be_duplicated_under_another_slug(self):
        self.db.add(Product(slug='another-notebook',title='Other notebook',supplier='printify',printify_product_id=self.notebook['printify_id']))
        self.db.commit()
        with self.assertRaisesRegex(ValueError,'another listing'):
            release.apply_product(self.db,self.notebook,notebook=self.info)

    def test_existing_listing_cannot_change_its_supplier_product(self):
        self.db.add(Product(slug=self.notebook['slug'],title='Existing notebook',supplier='printify',printify_product_id='different-supplier-product'))
        self.db.commit()
        with self.assertRaisesRegex(ValueError,'another Printify product'):
            release.apply_product(self.db,self.notebook,notebook=self.info)


class SupplierGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _, _, self.notebook = release.read_spec()
        self.product = {'id': self.notebook['printify_id'], 'blueprint_id': 485, 'print_provider_id': 28,
                        'variants': [{'id': 65223, 'is_enabled': True, 'is_available': True, 'cost': 1059, 'price':2799}],
                        'print_areas': [{'variant_ids': [65223], 'placeholders': [
                            {'position': 'front', 'images': [{'id': self.notebook['artwork_upload_id'], 'x':0.5,'y':0.5,'scale':1,'angle':0}]}]}]}

    async def test_unavailable_variant_blocks_release_before_shipping_call(self):
        self.product['variants'][0]['is_available'] = False
        with patch.object(release.printify, '_request', AsyncMock(return_value=self.product)), \
                patch.object(release.printify, 'shipping_cost', AsyncMock()) as shipping:
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                await release.notebook_info(self.notebook)
            shipping.assert_not_awaited()

    async def test_wrong_original_artwork_is_rejected(self):
        self.product['print_areas'][0]['placeholders'][0]['images'][0]['id'] = 'wrong-art'
        with patch.object(release.printify, '_request', AsyncMock(return_value=self.product)):
            with self.assertRaisesRegex(ValueError, 'artwork'):
                await release.notebook_info(self.notebook)

    async def test_cost_increase_blocks_publication(self):
        with patch.object(release.printify, '_request', AsyncMock(return_value=self.product)), \
                patch.object(release.printify, 'shipping_cost', AsyncMock(return_value=10)):
            with self.assertRaisesRegex(ValueError, 'cost limit'):
                await release.notebook_info(self.notebook)


    async def test_changed_full_wrap_placement_blocks_publication(self):
        self.product['print_areas'][0]['placeholders'][0]['images'][0]['scale']=0.6
        with patch.object(release.printify,'_request',AsyncMock(return_value=self.product)):
            with self.assertRaisesRegex(ValueError,'placement'):
                await release.notebook_info(self.notebook)

    async def test_lulu_cost_above_reviewed_limit_blocks_publication(self):
        _,book,_=release.read_spec()
        with patch.object(release.lulu,'cost',AsyncMock(return_value={'total_cost_incl_tax':'18.00'})):
            with self.assertRaisesRegex(ValueError,'cost limit'):
                await release.book_quote(book)

    async def test_lulu_current_cost_is_returned_for_fulfillment(self):
        _,book,_=release.read_spec()
        with patch.object(release.lulu,'cost',AsyncMock(return_value={'total_cost_incl_tax':'13.19','line_item_costs':[{'total_cost_excl_tax':'5.99'}]})):
            quote=await release.book_quote(book)
        self.assertEqual(quote,{'total_usd_example':13.19,'print_cost_usd':5.99})


if __name__ == '__main__':
    unittest.main()
