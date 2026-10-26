"""Supplier API pass-through: guards, write codes, blocked orders, redaction."""
import json
import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import main
from services import cj, etsy, lulu, pinterest, supplier_api
from fastapi.testclient import TestClient

KEY = 'k' * 40
REAL_CLIENT = httpx.AsyncClient

class SupplierApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app);self.addCleanup(self.client.close)
        directory = tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        key = Path(directory.name) / 'draft_key';key.write_text(KEY)
        env = patch.dict(os.environ, {'TBW_DRAFT_KEY_FILE': str(key), 'PRINTIFY_API_TOKEN': 'printify-secret',
                                      'PRINTIFY_SHOP_ID': '99', 'TBW_SUPPLIER_ORDERS_ENABLED': ''})
        env.start();self.addCleanup(env.stop)
        main._USED_CODES.clear()
        self.requests = []
        def handler(request):
            self.requests.append(request)
            return httpx.Response(200, json={'id': 1, 'address1': '1 Main St', 'email': 'a@b.c',
                                             'line_items': [{'first_name': 'Ana', 'sku': 'X'}]})
        p = patch.object(supplier_api.httpx, 'AsyncClient',
                         lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != 'transport'}))
        p.start();self.addCleanup(p.stop)

    def call(self, supplier, body, preview=False, headers=None):
        return self.client.post(f'/api/internal/suppliers/{supplier}/api' + ('?preview=true' if preview else ''),
                                json=body, headers={'Authorization': 'Bearer ' + KEY} if headers is None else headers)

    def test_guards(self):
        get = {'method': 'GET', 'path': '/shops.json'}
        self.assertEqual(self.call('printify', get, headers={}).status_code, 401)
        self.assertEqual(self.call('printify', get, headers={'Authorization': 'Bearer ' + KEY, 'X-Real-IP': '1.2.3.4'}).status_code, 404)
        for supplier, body in [('amazon', get), ('printify', {'method': 'GET', 'path': 'https://evil.example/x'}),
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
                               ('lulu', '/print-jobs/'), ('prodigi', '/orders'), ('slant3d', '/orders/SLANT_1'),
                               ('printify', '/shops/99/orders/1/send_to_production.json'),
                               ('meta', '/act_123/campaigns'), ('meta', '/act_123/ads'),
                               ('pinterest', '/ad_accounts/1/campaigns'),
                               ('etsy', '/application/shops/1/receipts/2/tracking')]:
            self.assertEqual(self.call(supplier, {'method': 'POST', 'path': path, 'body': {}}, preview=True).status_code, 403)
        with patch.dict(os.environ, {'TBW_SUPPLIER_ORDERS_ENABLED': '1'}):
            self.assertEqual(self.call('prodigi', {'method': 'POST', 'path': '/orders', 'body': {}}, preview=True).status_code, 200)
        self.assertEqual(self.requests, [])

    def test_slant3d_drafts_are_allowed_but_processing_stays_blocked(self):
        draft = {'method': 'POST', 'path': '/orders', 'body': {'items': []}}
        self.assertEqual(self.call('slant3d', draft, preview=True).status_code, 200)
        for method, path in (('POST', '/orders/SLANT_1'), ('DELETE', '/orders/SLANT_1'), ('POST', '/orders/batch')):
            self.assertEqual(self.call('slant3d', {'method': method, 'path': path, 'body': {}}, preview=True).status_code, 403)
        self.assertEqual(self.call('prodigi', draft, preview=True).status_code, 403)
        self.assertEqual(self.requests, [])

    def test_each_supplier_uses_its_own_auth(self):
        with patch.object(cj, 'get_access_token', AsyncMock(return_value='cj-token')), \
                patch.object(lulu, 'configured', return_value=True), \
                patch.object(lulu, '_token', AsyncMock(return_value='lulu-token')), \
                patch.dict(os.environ, {'PRODIGI_API_KEY_FILE': '', 'PRODIGI_API_KEY': 'prodigi-key', 'CREDENTIALS_DIRECTORY': '',
                                        'SLANT3D_API_KEY': 'sl_test'}):
            for supplier in ('cj', 'lulu', 'prodigi', 'slant3d'):
                self.assertEqual(self.call(supplier, {'method': 'GET', 'path': '/x'}).json()['status'], 200)
        cj_req, lulu_req, prodigi_req, slant_req = self.requests
        self.assertEqual(cj_req.headers['CJ-Access-Token'], 'cj-token')
        self.assertTrue(str(cj_req.url).startswith('https://developers.cjdropshipping.com/api2.0/v1/x'))
        self.assertEqual(lulu_req.headers['Authorization'], 'Bearer lulu-token')
        self.assertEqual(prodigi_req.headers['X-API-Key'], 'prodigi-key')
        self.assertEqual(str(prodigi_req.url), 'https://api.prodigi.com/v4.0/x')
        self.assertEqual(slant_req.headers['Authorization'], 'Bearer sl_test')
        self.assertEqual(str(slant_req.url), 'https://slant3dapi.com/v2/api/x')

    def test_supplier_failures_are_generic(self):
        with patch.object(cj, 'get_access_token', AsyncMock(side_effect=cj.CJError('secret detail'))):
            response = self.call('cj', {'method': 'GET', 'path': '/x'})
        self.assertEqual(response.status_code, 502);self.assertNotIn('secret', response.text)

    def test_etsy_meta_and_pinterest_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'etsy_token.json'
            token.write_text(json.dumps({'access_token': 'old', 'refresh_token': 'r1', 'expires_at': 0}))
            refreshed = []
            def handler(request):
                if request.url.path == '/v3/public/oauth/token':
                    refreshed.append(dict(x.split('=') for x in request.content.decode().split('&')))
                    return httpx.Response(200, json={'access_token': 'new', 'refresh_token': 'r2', 'expires_in': 3600})
                self.requests.append(request)
                return httpx.Response(200, json={'id': 1, 'access_token': 'page-token-leak'})
            with patch.object(supplier_api.httpx, 'AsyncClient',
                              lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != 'transport'})), \
                    patch.object(pinterest, 'access_token', AsyncMock(return_value='pin-token')), \
                    patch.dict(os.environ, {'ETSY_API_KEY': 'keystring:secret', 'ETSY_TOKEN_FILE': str(token),
                                            'FB_PAGE_TOKEN': 'page-token'}):
                for supplier, path in (('etsy', '/application/shops/1/listings'), ('meta', '/123/feed'), ('pinterest', '/boards')):
                    data = self.call(supplier, {'method': 'GET', 'path': path}).json()
                    self.assertEqual(data['data'], {'id': 1, 'access_token': '[redacted]'})
                saved = json.loads(token.read_text())
        etsy_req, meta_req, pin_req = self.requests
        self.assertEqual(refreshed[0]['client_id'], 'keystring');self.assertEqual(refreshed[0]['refresh_token'], 'r1')
        self.assertEqual((saved['access_token'], saved['refresh_token']), ('new', 'r2'))
        self.assertGreater(saved['expires_at'], time.time())
        self.assertEqual(etsy_req.headers['x-api-key'], 'keystring:secret')
        self.assertEqual(etsy_req.headers['Authorization'], 'Bearer new')
        self.assertEqual(str(etsy_req.url), 'https://openapi.etsy.com/v3/application/shops/1/listings')
        self.assertEqual(str(meta_req.url), 'https://graph.facebook.com/v21.0/123/feed')
        self.assertEqual(meta_req.headers['Authorization'], 'Bearer page-token')
        self.assertEqual(pin_req.headers['Authorization'], 'Bearer pin-token')

    def test_unconnected_services_fail_cleanly(self):
        with patch.dict(os.environ, {'ETSY_API_KEY': '', 'FB_PAGE_TOKEN': ''}):
            for supplier in ('etsy', 'meta'):
                response = self.call(supplier, {'method': 'GET', 'path': '/x'})
                self.assertEqual(response.status_code, 502)
        with patch.object(pinterest, 'access_token', AsyncMock(side_effect=main.HTTPException(401, 'run OAuth'))):
            self.assertEqual(self.call('pinterest', {'method': 'GET', 'path': '/boards'}).status_code, 502)
        self.assertEqual(self.requests, [])

if __name__ == '__main__':
    unittest.main()
