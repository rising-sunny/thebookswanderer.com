"""Internal CJ drafts: key and proxy guards, hidden rows, preview writes nothing."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from database import Base, get_db
from models import Product, ProductVariant
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

KEY = 'k' * 40
DETAILS = {
    'pid': 'PID-1', 'productNameEn': 'Walnut Book Stand', 'productSku': 'CJ1',
    'bigImage': 'https://img.example/big.jpg', 'productImageSet': ['https://img.example/a.jpg'],
    'variants': [
        {'vid': 'V1', 'variantKey': 'Small', 'variantSku': 'CJ1-S', 'variantSellPrice': 8.0,
         'variantImage': 'https://img.example/s.jpg'},
        {'vid': 'V2', 'variantKey': 'Large', 'variantSku': 'CJ1-L', 'variantSellPrice': 12.0},
    ],
}

class Drafts(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine);self.addCleanup(self.engine.dispose)
        def database():
            with self.sessions() as db:yield db
        main.app.dependency_overrides[get_db] = database
        self.addCleanup(main.app.dependency_overrides.clear)
        self.client = TestClient(main.app);self.addCleanup(self.client.close)
        directory = tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.key_file = Path(directory.name) / 'draft_key';self.key_file.write_text(KEY + '\n')
        env = patch.dict(os.environ, {'TBW_DRAFT_KEY_FILE': str(self.key_file)});env.start();self.addCleanup(env.stop)
        self.cj = AsyncMock(return_value=DETAILS)
        p = patch.object(main.cj_service, 'get_product_details', self.cj);p.start();self.addCleanup(p.stop)

    def post(self, preview=False, headers=None, **body):
        return self.client.post('/api/internal/drafts' + ('?preview=true' if preview else ''),
                                json={'cj_pid': 'PID-1', **body},
                                headers={'Authorization': 'Bearer ' + KEY} if headers is None else headers)

    def count(self):
        with self.sessions() as db:return db.query(Product).count()

    def test_rejects_missing_wrong_or_proxied_keys(self):
        self.assertEqual(self.post(headers={}).status_code, 401)
        self.assertEqual(self.post(headers={'Authorization': 'Bearer ' + 'x' * 40}).status_code, 401)
        proxied = {'Authorization': 'Bearer ' + KEY, 'X-Real-IP': '203.0.113.9'}
        self.assertEqual(self.post(headers=proxied).status_code, 404)
        self.key_file.write_text('short')
        self.assertEqual(self.post().status_code, 503)
        self.cj.assert_not_awaited();self.assertEqual(self.count(), 0)

    def test_preview_writes_nothing(self):
        response = self.post(preview=True)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['created'])
        self.assertEqual(data['preview']['product']['slug'], 'walnut-book-stand')
        self.assertEqual([v['name'] for v in data['preview']['variants']], ['Small', 'Large'])
        self.assertEqual(self.count(), 0)

    def test_creates_hidden_unpinned_draft_once(self):
        with patch('services.pinterest_jobs.pin_product_launch', AsyncMock()) as pin:
            response = self.post(price_usd=24.99, category='book-accessories')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['created']);self.assertEqual(data['variants'], 2)
        pin.assert_not_awaited()
        with self.sessions() as db:
            product = db.query(Product).one()
            self.assertFalse(product.active);self.assertTrue(product.draft)
            self.assertEqual(product.price_usd, 24.99);self.assertEqual(product.description, '')
            self.assertEqual(db.query(ProductVariant).filter_by(product_id=product.id).count(), 2)
        self.assertEqual(self.client.get('/api/products/by-slug/walnut-book-stand').status_code, 404)
        again = self.post().json()
        self.assertFalse(again['created']);self.assertTrue(again['existing']['draft'])
        self.assertEqual(self.count(), 1);self.assertEqual(self.cj.await_count, 1)

    def test_validates_input(self):
        self.assertEqual(self.post(cj_pid='../x').status_code, 422)
        self.assertEqual(self.post(price_usd=0).status_code, 422)
        self.cj.assert_not_awaited()

    def draft_id(self):
        self.assertTrue(self.post(price_usd=24.99).json()['created'])
        with self.sessions() as db:return db.query(Product).one().id

    def call(self, path, body=None, preview=False):
        return self.client.post(f'/api/internal/drafts/{path}' + ('?preview=true' if preview else ''),
                                json=body, headers={'Authorization': 'Bearer ' + KEY})

    def test_update_edits_only_drafts(self):
        pid = self.draft_id()
        response = self.call(f'{pid}/update', {'title': 'Little House Bookends', 'category': 'Book-Accessories',
                                               'description': 'A small wooden house.', 'price_usd': 19.5})
        self.assertEqual(response.status_code, 200)
        draft = response.json()['draft']
        self.assertEqual((draft['slug'], draft['category']), ('little-house-bookends', 'book-accessories'))
        self.assertEqual({v['price_usd'] for v in draft['variants']}, {19.5})
        self.assertIn('description is missing or shorter than 40 characters', response.json()['problems'])
        self.assertEqual(self.call(f'{pid}/update', {'category': 'toys'}).status_code, 422)
        with self.sessions() as db:
            archived = Product(slug='old', title='Old', active=False, draft=False)
            live = Product(slug='live', title='Live', active=True, draft=False)
            db.add_all([archived, live]);db.commit();ids = (archived.id, live.id)
        for other in ids:
            self.assertEqual(self.call(f'{other}/update', {'title': 'Changed'}).status_code, 404)
            self.assertEqual(self.call(f'{other}/publish', preview=True).status_code, 404)
        self.assertEqual(self.client.post(f'/api/internal/drafts/{pid}/update', json={'title': 'Nope'},
                                          headers={'Authorization': 'Bearer ' + KEY, 'X-Real-IP': '203.0.113.9'}).status_code, 404)

    def test_publish_needs_ready_draft_and_current_code(self):
        pid = self.draft_id()
        preview = self.call(f'{pid}/publish', preview=True).json()
        self.assertIsNone(preview['code']);self.assertTrue(preview['problems'])
        self.assertEqual(self.call(f'{pid}/publish', {'code': 'ABC123'}).status_code, 409)
        self.call(f'{pid}/update', {'category': 'book-accessories',
                                     'description': 'A small wooden house that keeps a shelf of books upright.'})
        code = self.call(f'{pid}/publish', preview=True).json()['code']
        self.assertRegex(code, r'^[0-9A-F]{6}$')
        self.call(f'{pid}/update', {'price_usd': 26.0})
        self.assertEqual(self.call(f'{pid}/publish', {'code': code}).status_code, 409)
        with self.sessions() as db:self.assertFalse(db.get(Product, pid).active)
        code = self.call(f'{pid}/publish', preview=True).json()['code']
        response = self.call(f'{pid}/publish', {'code': code.lower()})
        self.assertEqual(response.status_code, 200);self.assertTrue(response.json()['published'])
        with self.sessions() as db:
            product = db.get(Product, pid);self.assertTrue(product.active);self.assertFalse(product.draft)
        self.assertEqual(self.client.get('/api/products/by-slug/walnut-book-stand').status_code, 200)
        self.assertEqual(self.call(f'{pid}/publish', {'code': code}).status_code, 404)

if __name__ == '__main__':
    unittest.main()
