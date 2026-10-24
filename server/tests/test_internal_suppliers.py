"""Internal supplier reads: key guard, read-only calls, trimmed and sanitized output."""
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
from services import printify, prodigi_store, shipping
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

KEY = 'k' * 40
SHOP = {'id': 'abc123', 'title': 'Tote', 'visible': True, 'images': [1, 2], 'variants': [
    {'id': 1, 'title': 'S', 'cost': 1250, 'price': 2799, 'is_enabled': True},
    {'id': 2, 'title': 'XL', 'cost': 1400, 'price': 2999, 'is_enabled': False},
]}

class Suppliers(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine);self.addCleanup(self.engine.dispose)
        with self.sessions() as db:
            p = Product(slug='tote', title='Tote', supplier='printify', printify_product_id='abc123',
                        price_usd=27.99, active=False, draft=True)
            p.variants = [ProductVariant(name='S', price_usd=27.99, active=True)]
            db.add(p);db.commit();self.pid = p.id
        def database():
            with self.sessions() as db:yield db
        main.app.dependency_overrides[get_db] = database
        self.addCleanup(main.app.dependency_overrides.clear)
        self.client = TestClient(main.app);self.addCleanup(self.client.close)
        directory = tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        key = Path(directory.name) / 'draft_key';key.write_text(KEY)
        env = patch.dict(os.environ, {'TBW_DRAFT_KEY_FILE': str(key), 'PRINTIFY_SHOP_ID': '99'});env.start();self.addCleanup(env.stop)

    def post(self, path, body=None, headers=None):
        return self.client.post('/api/internal' + path, json=body,
                                headers={'Authorization': 'Bearer ' + KEY} if headers is None else headers)

    def test_all_routes_need_the_key_and_loopback(self):
        with patch.object(printify, '_request', AsyncMock()) as api:
            for path in ('/suppliers/printify/products', '/suppliers/printify/products/abc123',
                         '/suppliers/prodigi/products/GLOBAL-FAP-12X16'):
                self.assertEqual(self.post(path, headers={}).status_code, 401)
                self.assertEqual(self.post(path, headers={'Authorization': 'Bearer ' + KEY,
                                                          'X-Forwarded-For': '203.0.113.9'}).status_code, 404)
            api.assert_not_awaited()

    def test_printify_reads_are_gets_and_mark_store_products(self):
        api = AsyncMock(side_effect=[{'data': [SHOP], 'last_page': 1}, SHOP])
        with patch.object(printify, '_request', api):
            listing = self.post('/suppliers/printify/products', {'page': 2, 'limit': 5}).json()
            detail = self.post('/suppliers/printify/products/abc123').json()
        self.assertEqual([c.args for c in api.await_args_list], [
            ('GET', '/shops/99/products.json?page=2&limit=5'), ('GET', '/shops/99/products/abc123.json')])
        self.assertEqual(listing['products'][0], {'id': 'abc123', 'title': 'Tote', 'visible': True,
            'enabled_variants': 1, 'cost_usd_min': 12.5, 'price_usd_min': 27.99, 'in_store': True})
        self.assertEqual(detail['variants'], [{'id': 1, 'title': 'S', 'cost_usd': 12.5, 'price_usd': 27.99}])
        self.assertEqual(self.post('/suppliers/printify/products/..%2Fx').status_code, 404)

    def test_supplier_errors_are_sanitized(self):
        with patch.object(printify, '_request', AsyncMock(side_effect=printify.PrintifyError('secret-token'))):
            response = self.post('/suppliers/printify/products')
        self.assertEqual(response.status_code, 502);self.assertNotIn('secret', response.text)

    def test_prodigi_product_summary(self):
        data = {'outcome': 'Ok', 'product': {'sku': 'GLOBAL-FAP-12X16', 'description': 'Fine art print',
                'printAreas': {'default': {}}, 'variants': [
                    {'attributes': {'paper': 'EMA'}, 'shipsTo': ['US', 'GB']},
                    {'attributes': {'paper': 'HPR'}, 'shipsTo': ['US']}]}}
        with patch.object(prodigi_store, 'request', AsyncMock(return_value=data)) as api:
            out = self.post('/suppliers/prodigi/products/GLOBAL-FAP-12X16').json()
        api.assert_awaited_once_with('GET', '/products/GLOBAL-FAP-12X16')
        self.assertEqual(out['ships_to'], ['GB', 'US']);self.assertEqual(out['print_areas'], ['default'])
        self.assertEqual(len(out['variants']), 2)

    def test_shipping_quote_covers_drafts_and_unavailable_routes(self):
        result = {'shipping_total': 4.5, 'legs': []}
        with patch.object(shipping, 'quote', AsyncMock(return_value=result)) as quote:
            out = self.post(f'/shipping/{self.pid}', {'country_code': 'mx'}).json()
        self.assertTrue(out['available']);self.assertEqual(out['supplier'], 'printify')
        self.assertEqual(quote.await_args.args[1], 'mx')
        error = shipping.QuoteError('no route', status=400, reason='no_route')
        with patch.object(shipping, 'quote', AsyncMock(side_effect=error)):
            out = self.post(f'/shipping/{self.pid}', {'country_code': 'KP'}).json()
        self.assertFalse(out['available']);self.assertEqual(out['reason'], 'no_route')
        self.assertEqual(self.post('/shipping/999', {'country_code': 'US'}).status_code, 404)
        self.assertEqual(self.post(f'/shipping/{self.pid}', {'country_code': 'USA'}).status_code, 422)

if __name__ == '__main__':
    unittest.main()
