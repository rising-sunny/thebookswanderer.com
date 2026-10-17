"""Release safeguards for supplier artwork and repeatable checkout mappings."""
import copy
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from database import Base
from models import Product, ProductVariant
import publish_reading_stationery as release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.spec = release.read_spec()[0]

    def supplier_product(self):
        s = self.spec
        return {
            'id': s['printify_id'], 'blueprint_id': s['blueprint_id'], 'print_provider_id': s['provider_id'],
            'variants': [{'id': s['variant_id'], 'price': round(s['price_usd'] * 100),
                          'cost': 695, 'is_enabled': True, 'is_available': True}],
            'print_areas': [{'variant_ids': [s['variant_id']], 'placeholders': [
                {'position': side, 'images': [{'id': u['id'], 'width': u['width'], 'height': u['height'],
                                               'x': .5, 'y': .5, 'scale': 1, 'angle': 0}]}
                for side, u in s['uploads'].items()
            ]}],
        }

    def test_fulfillment_rejects_unavailable_or_wrong_variant_and_price(self):
        self.assertEqual(release.verify_supplier(self.spec, self.supplier_product()), 6.95)
        for field, value in [('id', 1), ('is_available', False), ('price', 100)]:
            p = self.supplier_product()
            p['variants'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                release.verify_supplier(self.spec, p)

    def test_print_placement_or_upload_changes_block_publication(self):
        for field, value in [('id', 'different-artwork'), ('scale', .8), ('x', .4), ('flipX', True)]:
            p = self.supplier_product()
            p['print_areas'][0]['placeholders'][0]['images'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                release.verify_supplier(self.spec, p)

    def test_republish_keeps_existing_product_and_checkout_variant_ids(self):
        engine = create_engine('sqlite://')
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        info = {'cost_usd': 6.95, 'shipping_usd': 5.69}
        with sessions() as db:
            p = release.apply_product(db, self.spec, info)
            db.commit()
            product_id = p.id
            variant_id = p.default_variant().id
            release.apply_product(db, self.spec, info)
            db.commit()
            self.assertEqual(db.query(Product).count(), 1)
            self.assertEqual(db.query(ProductVariant).count(), 1)
            self.assertEqual(p.id, product_id)
            self.assertEqual(p.default_variant().id, variant_id)
            self.assertEqual(p.default_variant().printify_variant_id, self.spec['variant_id'])

    def test_existing_slug_or_supplier_mapping_is_not_overwritten(self):
        engine = create_engine('sqlite://')
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        for same_slug in (True, False):
            with sessions() as db:
                p = Product(slug=self.spec['slug'] if same_slug else 'another-product', title='Original',
                            supplier='cj' if same_slug else 'printify',
                            printify_product_id='' if same_slug else self.spec['printify_id'])
                db.add(p)
                db.commit()
                with self.assertRaises(ValueError):
                    release.apply_product(db, self.spec, {'cost_usd': 6.95})
                self.assertEqual(p.title, 'Original')
                db.delete(p)
                db.commit()


if __name__ == '__main__':
    unittest.main()
