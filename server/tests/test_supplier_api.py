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

    def test_receipt_and_shipping_address_names_are_hidden(self):
        from services.supplier_api import redact
        receipt = {"receipt_id": 1, "name": "Jane Doe", "first_line": "1 Main St", "second_line": "",
                   "city": "Springfield", "state": "OH", "zip": "00000", "country_iso": "US",
                   "formatted_address": "Jane Doe\n1 Main St", "buyer_email": "j@example.com",
                   "transactions": [{"title": "Book", "sku": "X", "variations": [{"formatted_name": "Size"}]}]}
        out = redact(receipt)
        for key in ("name", "first_line", "second_line", "city", "zip", "formatted_address", "buyer_email"):
            self.assertEqual(out[key], "[redacted]", key)
        self.assertEqual((out["state"], out["country_iso"], out["transactions"][0]["title"]), ("OH", "US", "Book"))
        lulu = redact({"shipping_address": {"name": "Sam", "street1": "x", "city": "Y", "country_code": "US"},
                       "status": {"name": "SHIPPED"}})
        self.assertEqual(lulu["shipping_address"], "[redacted]")
        self.assertEqual(lulu["status"]["name"], "SHIPPED")
        options = redact({"options": [{"name": "Clothing sizes", "values": [{"title": "S"}]}], "name": "Board"})
        self.assertEqual((options["options"][0]["name"], options["name"]), ("Clothing sizes", "Board"))
        nested = redact({"to": {"name": "Ann", "line1": "2 Elm", "city": "Z", "country": "US"}})
        self.assertEqual((nested["to"]["name"], nested["to"]["city"], nested["to"]["country"]), ("[redacted]", "[redacted]", "US"))

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

    def test_meta_ads_only_paused_and_within_the_daily_budget_limit(self):
        def status(path, body, method='POST'):
            return self.call('meta', {'method': method, 'path': path, 'body': body}, preview=True).status_code
        paused = {'name': 'x', 'objective': 'OUTCOME_TRAFFIC', 'status': 'PAUSED', 'daily_budget': 5000}
        self.assertEqual(status('/act_123/campaigns', paused), 403)          # limit unset: blocked
        with patch.dict(os.environ, {'TBW_META_ADS_MAX_DAILY_BUDGET': '15000'}):
            self.assertEqual(status('/act_123/campaigns', paused), 200)
            self.assertEqual(status('/act_123/adsets', {**paused, 'targeting': {'geo_locations': {'countries': ['US']}}}), 200)
            self.assertEqual(status('/act_123/adcreatives', {'name': 'c', 'object_story_spec': {}}), 200)
            self.assertEqual(status('/act_123/campaigns', {**paused, 'status': 'ACTIVE'}), 403)
            self.assertEqual(status('/act_123/ads', {'name': 'a', 'creative': {'creative_id': '1'}}), 403)
            self.assertEqual(status('/act_123/campaigns', {**paused, 'daily_budget': 15001}), 403)
            self.assertEqual(status('/act_123/campaigns', {**paused, 'lifetime_budget': 100}), 403)
            self.assertEqual(status('/120249986543080256', {'status': 'ACTIVE'}), 403)
            self.assertEqual(status('/120249986543080256', {'status': 'PAUSED'}), 200)
            self.assertEqual(status('/120249986543080256', {'name': 'renamed'}), 200)
            self.assertEqual(status('/act_123/campaigns', paused, method='DELETE'), 403)
        self.assertEqual(status('/120249986543080256', {'status': 'ACTIVE'}), 403)  # never, even when unset
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

    def test_meta_video_uploads_from_a_file_inside_the_assets_folder_only(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / 'products').mkdir()
            (assets / 'products' / 'ad.mp4').write_bytes(b'FAKE-VIDEO-BYTES')
            (assets / 'products' / 'notes.txt').write_text('x')
            (assets.parent / 'outside.mp4').write_bytes(b'secret')
            self.addCleanup(lambda: (assets.parent / 'outside.mp4').unlink(missing_ok=True))
            path = '/act_123/advideos'
            def send(body, p=path, preview=True, code=None, method='POST'):
                data = {'method': method, 'path': p, 'body': body}
                if code: data['code'] = code
                return self.call('meta', data, preview=preview)
            ok = {'local_file': 'products/ad.mp4', 'title': 'Math Art', 'published': False}
            with patch.object(supplier_api, 'ASSETS_DIR', assets), \
                    patch.dict(os.environ, {'FB_PAGE_TOKEN': 'page-token', 'TBW_META_ADS_MAX_DAILY_BUDGET': '15000'}):
                for bad in ({'local_file': '../outside.mp4'}, {'local_file': '/etc/passwd'}, {'local_file': 'products/notes.txt'},
                            {'local_file': 'products/missing.mp4'}, {'local_file': 5},
                            {**ok, 'file_url': 'https://example.com/a.mp4'}):
                    self.assertEqual(send(bad).status_code, 422, bad)
                self.assertEqual(send(ok, p='/act_123/adimages').status_code, 422)
                self.assertEqual(send(ok, p='/123/videos').status_code, 422)
                self.assertEqual(send(ok, method='PUT').status_code, 422)
                self.assertEqual(self.requests, [])
                preview = send(ok)
                self.assertEqual(preview.status_code, 200)
                self.assertFalse(preview.json()['executed'])
                self.assertEqual(self.requests, [])
                done = send(ok, preview=False, code=preview.json()['code'])
        self.assertEqual(done.status_code, 200)
        request = self.requests[0]
        self.assertEqual(str(request.url), 'https://graph.facebook.com/v21.0/act_123/advideos')
        self.assertEqual(request.headers['Authorization'], 'Bearer page-token')
        self.assertTrue(request.headers['Content-Type'].startswith('multipart/form-data'))
        body = request.content
        self.assertIn(b'FAKE-VIDEO-BYTES', body)
        self.assertIn(b'name="source"', body)
        self.assertIn(b'name="title"', body)
        self.assertIn(b'Math Art', body)
        self.assertIn(b'name="published"', body)
        self.assertIn(b'false', body)
        self.assertNotIn(b'local_file', body)

    def test_page_reel_runs_start_upload_publish_for_the_configured_page_only(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / 'products').mkdir()
            (assets / 'products' / 'reel.mp4').write_bytes(b'FAKE-REEL-BYTES')
            seen = []
            def handler(request):
                seen.append(request)
                if request.url.host == 'rupload.facebook.com':
                    return httpx.Response(200, json={'success': True})
                if b'upload_phase=start' in request.content:
                    return httpx.Response(200, json={'video_id': '777', 'upload_url': 'https://x'})
                return httpx.Response(200, json={'success': True})
            def send(body, p='/12345/video_reels', preview=True, code=None, method='POST'):
                data = {'method': method, 'path': p, 'body': body}
                if code: data['code'] = code
                return self.call('meta', data, preview=preview)
            ok = {'local_file': 'products/reel.mp4', 'description': 'A mug. https://example.com/p?utm_source=facebook'}
            with patch.object(supplier_api, 'ASSETS_DIR', assets), \
                    patch.object(supplier_api.httpx, 'AsyncClient',
                                 lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != 'transport'})), \
                    patch.dict(os.environ, {'FB_PAGE_TOKEN': 'page-token', 'FB_PAGE_ID': '12345'}):
                for bad, kw in ((ok, {'p': '/99999/video_reels'}), (ok, {'method': 'PUT'}), (ok, {'p': '/12345/video_reels?x=1'}),
                                ({**ok, 'title': 'T'}, {}), ({'local_file': ok['local_file']}, {}),
                                ({**ok, 'description': ''}, {}), ({**ok, 'description': 'x' * 2001}, {}),
                                ({**ok, 'file_url': 'https://example.com/a.mp4'}, {}),
                                ({**ok, 'local_file': '../outside.mp4'}, {}), ({**ok, 'local_file': 'products/missing.mp4'}, {})):
                    self.assertEqual(send(bad, **kw).status_code, 422, (bad, kw))
                self.assertEqual(seen, [])
                preview = send(ok)
                self.assertEqual(preview.status_code, 200)
                self.assertFalse(preview.json()['executed']);self.assertEqual(seen, [])
                done = send(ok, preview=False, code=preview.json()['code'])
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json()['data'], {'success': True, 'video_id': '777'})
        self.assertEqual([str(r.url) for r in seen], [
            'https://graph.facebook.com/v21.0/12345/video_reels',
            'https://rupload.facebook.com/video-upload/v21.0/777',
            'https://graph.facebook.com/v21.0/12345/video_reels'])
        self.assertEqual(seen[0].headers['Authorization'], 'Bearer page-token')
        self.assertEqual(seen[1].headers['Authorization'], 'OAuth page-token')
        self.assertEqual((seen[1].headers['offset'], seen[1].headers['file_size']), ('0', str(len(b'FAKE-REEL-BYTES'))))
        self.assertEqual(seen[1].content, b'FAKE-REEL-BYTES')
        for needle in (b'upload_phase=finish', b'video_id=777', b'video_state=PUBLISHED', b'description=A+mug'):
            self.assertIn(needle, seen[2].content)
        self.assertNotIn(b'local_file', seen[2].content)

    def test_page_reel_reports_the_first_failing_step(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / 'reel.mp4').write_bytes(b'X')
            seen = []
            def handler(request):
                seen.append(request)
                return httpx.Response(400, json={'error': {'message': 'start refused'}})
            body = {'local_file': 'reel.mp4', 'description': 'Hi'}
            with patch.object(supplier_api, 'ASSETS_DIR', assets), \
                    patch.object(supplier_api.httpx, 'AsyncClient',
                                 lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != 'transport'})), \
                    patch.dict(os.environ, {'FB_PAGE_TOKEN': 'page-token', 'FB_PAGE_ID': '12345'}):
                data = {'method': 'POST', 'path': '/12345/video_reels', 'body': body}
                code = self.call('meta', data, preview=True).json()['code']
                done = self.call('meta', {**data, 'code': code})
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json()['status'], 400)
        self.assertEqual(len(seen), 1)

    def test_etsy_listing_video_uploads_from_the_assets_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / 'ad.mp4').write_bytes(b'FAKE-VIDEO-BYTES')
            token = assets / 'etsy_token.json'
            token.write_text(json.dumps({'access_token': 'tok', 'refresh_token': 'r1', 'expires_at': 9999999999}))
            path = '/application/shops/66586766/listings/4544209146/videos'
            def send(body, p=path, preview=True, code=None):
                data = {'method': 'POST', 'path': p, 'body': body}
                if code: data['code'] = code
                return self.call('etsy', data, preview=preview)
            ok = {'local_file': 'ad.mp4', 'name': 'Book'}
            def handler(request):
                self.requests.append(request)
                return httpx.Response(201, json={'video_id': 1})
            with patch.object(supplier_api, 'ASSETS_DIR', assets), \
                    patch.object(supplier_api.httpx, 'AsyncClient',
                                 lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != 'transport'})), \
                    patch.dict(os.environ, {'ETSY_API_KEY': 'keystring:secret', 'ETSY_TOKEN_FILE': str(token)}):
                self.assertEqual(send({'local_file': '../x.mp4'}).status_code, 422)
                self.assertEqual(send(ok, p='/application/shops/66586766/listings/4544209146').status_code, 422)
                self.assertEqual(self.requests, [])
                preview = send(ok)
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(self.requests, [])
                done = send(ok, preview=False, code=preview.json()['code'])
        self.assertEqual(done.status_code, 200)
        request = self.requests[0]
        self.assertTrue(request.url.path.endswith('/listings/4544209146/videos'))
        self.assertTrue(request.headers['Content-Type'].startswith('multipart/form-data'))
        self.assertIn(b'name="video"', request.content)
        self.assertIn(b'FAKE-VIDEO-BYTES', request.content)
        self.assertNotIn(b'local_file', request.content)

    def test_alura_is_read_only_uses_the_server_key_and_reports_credits(self):
        seen = []
        def handler(request):
            seen.append(request)
            left = '5' if 'research/products' in request.url.path else '90'
            return httpx.Response(200, json={'keywords': [{'q': 'desk mat'}]},
                                  headers={'Alura-Credits-Cost': '1', 'Alura-Credits-Remaining': left})
        supplier_api._alura_remaining = None
        with patch.object(supplier_api.httpx, 'AsyncClient',
                          lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != 'transport'})), \
                patch.dict(os.environ, {'ALURA_API_KEY': 'alura_sk_secret', 'ALURA_MIN_CREDITS_RESERVE': '10'}):
            ok = self.call('alura', {'method': 'GET', 'path': '/research/keywords?q=desk%20mat&q=math%20gift'})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json()['credits'], {'cost': '1', 'remaining': '90'})
            self.assertNotIn('alura_sk_secret', ok.text)
            self.assertEqual(str(seen[0].url), 'https://api.alura.io/v1/research/keywords?q=desk%20mat&q=math%20gift')
            self.assertEqual(seen[0].headers['Authorization'], 'Bearer alura_sk_secret')
            # never a write, never a path outside the research and account reads
            self.assertEqual(self.call('alura', {'method': 'POST', 'path': '/research/saved/lists'}).status_code, 403)
            self.assertEqual(self.call('alura', {'method': 'DELETE', 'path': '/research/saved/lists/1'}).status_code, 403)
            for bad in ('/admin', '/me/workspace', '/research', '/research/../me'):
                self.assertEqual(self.call('alura', {'method': 'GET', 'path': bad}).status_code, 422, bad)
            n = len(seen)
            # a call that leaves only 5 credits: research stops, free account reads keep working
            self.assertEqual(self.call('alura', {'method': 'GET', 'path': '/research/products?q=desk'}).status_code, 200)
            self.assertEqual(self.call('alura', {'method': 'GET', 'path': '/research/keywords?q=x'}).status_code, 403)
            self.assertEqual(self.call('alura', {'method': 'GET', 'path': '/usage'}).status_code, 200)
            self.assertEqual(len(seen), n + 2)
        supplier_api._alura_remaining = None

    def test_alura_without_a_key_is_not_configured(self):
        supplier_api._alura_remaining = None
        with patch.dict(os.environ, {'ALURA_API_KEY': ''}):
            self.assertEqual(self.call('alura', {'method': 'GET', 'path': '/me'}).status_code, 502)
        self.assertEqual(self.requests, [])

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
