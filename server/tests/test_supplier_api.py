"""Supplier API pass-through: guards, write codes, blocked orders, redaction."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import main
from services import cj, lulu, supplier_api
from fastapi.testclient import TestClient

KEY = 'k' * 40

class SupplierApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app);self.addCleanup(self.client.close)
        directory = tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        key = Path(directory.name) / 'draft_key';key.write_text(KEY)
        env = patch.dict(os.environ, {'TBW_DRAFT_KEY_FILE': str(key), 'PRINTIFY_API_TOKEN': 'printify-secret',
                                      'PRINTIFY_SHOP_ID': '99', 'TBW_SUPPLIER_ORDERS_ENABLED': ''})
        env.start();self.addCleanup(env.stop)
        main._USED_SUPPLIER_CODES.clear()
        self.requests = []
        def handler(request):
            self.requests.append(request)
            return httpx.Response(200, json={'id': 1, 'address1': '1 Main St', 'email': 'a@b.c',
                                             'line_items': [{'first_name': 'Ana', 'sku': 'X'}]})
        real = httpx.AsyncClient
        p = patch.object(supplier_api.httpx, 'AsyncClient',
                         lambda **kw: real(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != 'transport'}))
        p.start();self.addCleanup(p.stop)

    def call(self, supplier, body, preview=False, headers=None):
        return self.client.post(f'/api/internal/suppliers/{supplier}/api' + ('?preview=true' if preview else ''),
                                json=body, headers={'Authorization': 'Bearer ' + KEY} if headers is None else headers)

    def test_guards(self):
        get = {'method': 'GET', 'path': '/shops.json'}
        self.assertEqual(self.call('printify', get, headers={}).status_code, 401)
        self.assertEqual(self.call('printify', get, headers={'Authorization': 'Bearer ' + KEY, 'X-Real-IP': '1.2.3.4'}).status_code, 404)
        for supplier, body in [('etsy', get), ('printify', {'method': 'GET', 'path': 'https://evil.example/x'}),
                               ('printify', {'method': 'GET', 'path': '/a/../b'}), ('printify', {'method': 'GET', 'path': '//evil'}),
                               ('printify', {'method': 'TRACE', 'path': '/x'})]:
            self.assertEqual(self.call(supplier, body).status_code, 422, (supplier, body))
        self.assertEqual(self.requests, [])

    def test_reads_go_through_with_the_store_key_and_lose_personal_data(self):
        response = self.call('printify', {'method': 'GET', 'path': '/shops/99/orders.json?page=1'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 200)
        self.assertEqual(data['data'], {'id': 1, 'address1': '[redacted]', 'email': '[redacted]',
                                        'line_items': [{'first_name': '[redacted]', 'sku': 'X'}]})
        self.assertEqual(str(self.requests[0].url), 'https://api.printify.com/v1/shops/99/orders.json?page=1')
        self.assertEqual(self.requests[0].headers['Authorization'], 'Bearer printify-secret')
        self.assertNotIn('printify-secret', response.text)

    def test_writes_need_a_fresh_single_use_code_for_the_exact_request(self):
        body = {'method': 'PUT', 'path': '/shops/99/products/abc.json', 'body': {'title': 'New'}}
        preview = self.call('printify', body, preview=True).json()
        self.assertFalse(preview['executed']);self.assertEqual(self.requests, [])
        code = preview['code']
        self.assertEqual(self.call('printify', body).status_code, 409)
        changed = dict(body, body={'title': 'Other'}, code=code)
        self.assertEqual(self.call('printify', changed).status_code, 409)
        self.assertEqual(self.call('printify', dict(body, code=code.lower())).json()['status'], 200)
        self.assertEqual(self.requests[0].method, 'PUT')
        self.assertEqual(self.call('printify', dict(body, code=code)).status_code, 409)  # used
        self.assertEqual(len(self.requests), 1)

    def test_orders_and_payments_stay_blocked_unless_enabled_on_the_vps(self):
        for supplier, path in [('printify', '/shops/99/orders.json'), ('cj', '/shopping/pay/payBalance'),
                               ('lulu', '/print-jobs/'), ('prodigi', '/orders'),
                               ('printify', '/shops/99/orders/1/send_to_production.json')]:
            self.assertEqual(self.call(supplier, {'method': 'POST', 'path': path, 'body': {}}, preview=True).status_code, 403)
        with patch.dict(os.environ, {'TBW_SUPPLIER_ORDERS_ENABLED': '1'}):
            self.assertEqual(self.call('prodigi', {'method': 'POST', 'path': '/orders', 'body': {}}, preview=True).status_code, 200)
        self.assertEqual(self.requests, [])

    def test_each_supplier_uses_its_own_auth(self):
        with patch.object(cj, 'get_access_token', AsyncMock(return_value='cj-token')), \
                patch.object(lulu, 'configured', return_value=True), \
                patch.object(lulu, '_token', AsyncMock(return_value='lulu-token')), \
                patch.dict(os.environ, {'PRODIGI_API_KEY_FILE': '', 'PRODIGI_API_KEY': 'prodigi-key', 'CREDENTIALS_DIRECTORY': ''}):
            for supplier in ('cj', 'lulu', 'prodigi'):
                self.assertEqual(self.call(supplier, {'method': 'GET', 'path': '/x'}).json()['status'], 200)
        cj_req, lulu_req, prodigi_req = self.requests
        self.assertEqual(cj_req.headers['CJ-Access-Token'], 'cj-token')
        self.assertTrue(str(cj_req.url).startswith('https://developers.cjdropshipping.com/api2.0/v1/x'))
        self.assertEqual(lulu_req.headers['Authorization'], 'Bearer lulu-token')
        self.assertEqual(prodigi_req.headers['X-API-Key'], 'prodigi-key')
        self.assertEqual(str(prodigi_req.url), 'https://api.prodigi.com/v4.0/x')

    def test_supplier_failures_are_generic(self):
        with patch.object(cj, 'get_access_token', AsyncMock(side_effect=cj.CJError('secret detail'))):
            response = self.call('cj', {'method': 'GET', 'path': '/x'})
        self.assertEqual(response.status_code, 502);self.assertNotIn('secret', response.text)

if __name__ == '__main__':
    unittest.main()
