"""Cross-listing with Etsy: Printify twins, Etsy drafts, codes and guards."""
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
from services import crosslist
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

KEY = 'k' * 40
SOURCE = {'id': 'etsyshopprod', 'title': 'Golden Ratio Print', 'blueprint_id': 5, 'print_provider_id': 9,
          'tags': ['math'], 'images': [{'src': 'https://img/mock.jpg'}],
          'variants': [{'id': 11, 'title': '8x10', 'cost': 900, 'price': 2500, 'is_enabled': True},
                       {'id': 12, 'title': '11x14', 'cost': 1200, 'price': 3200, 'is_enabled': False}],
          'print_areas': [{'variant_ids': [11, 12], 'placeholders': [
              {'position': 'front', 'images': [{'id': 'img1', 'x': .5, 'y': .5, 'scale': 1, 'angle': 0,
                                                'name': 'art.png', 'height': 10}]}]}]}
LISTING = {'listing_id': '42', 'title': 'Golden Ratio Print', 'description': 'Spirals &amp; shells',
           'price_usd': 25.0, 'is_digital': False, 'images': ['https://etsy/img1.jpg'],
           'variants': [{'name': '8x10', 'price_usd': 25.0}], 'url': 'https://etsy/listing/42'}

class CrossList(unittest.TestCase):
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
        self.dir = Path(directory.name)
        (self.dir / 'key').write_text(KEY)
        env = patch.dict(os.environ, {'TBW_DRAFT_KEY_FILE': str(self.dir / 'key'), 'PRINTIFY_SHOP_ID': '100',
                                      'PRINTIFY_ETSY_SHOP_ID': '200', 'ETSY_SHOP_ID': '300',
                                      'DIGITAL_DIR': str(self.dir)})
        env.start();self.addCleanup(env.stop)
        main._USED_CODES.clear()

    def mock(self, name, value):
        p = patch.object(crosslist, name, value);p.start();self.addCleanup(p.stop);return value

    def post(self, path, body, preview=False):
        return self.client.post('/api/internal/crosslist/' + path + ('?preview=true' if preview else ''),
                                json=body, headers={'Authorization': 'Bearer ' + KEY})

    def test_twin_payload_rebuilds_the_product(self):
        payload = crosslist.twin_payload(SOURCE, title='T' * 200, prices={11: 19.99})
        self.assertEqual(len(payload['title']), 140)
        self.assertEqual(payload['variants'], [{'id': 11, 'price': 1999, 'is_enabled': True},
                                               {'id': 12, 'price': 3200, 'is_enabled': False}])
        self.assertEqual(payload['print_areas'][0]['placeholders'][0]['images'],
                         [{'id': 'img1', 'x': .5, 'y': .5, 'scale': 1, 'angle': 0}])
        self.assertEqual((payload['blueprint_id'], payload['print_provider_id']), (5, 9))

    def test_twin_payload_drops_empty_positions(self):
        area = dict(SOURCE['print_areas'][0])
        area['placeholders'] = area['placeholders'] + [{'position': 'january_grid', 'images': []}]
        payload = crosslist.twin_payload(dict(SOURCE, print_areas=[area]))
        self.assertEqual([p['position'] for p in payload['print_areas'][0]['placeholders']], ['front'])

    def test_printify_listing_becomes_a_draft_with_a_twin_in_the_store_shop(self):
        self.mock('etsy_listing', AsyncMock(return_value=LISTING))
        self.mock('printify_for_listing', AsyncMock(return_value=SOURCE))
        create = self.mock('create_twin', AsyncMock(return_value=dict(SOURCE, id='storetwin')))
        preview = self.post('from-etsy', {'listing_id': '42'}, preview=True).json()
        self.assertEqual(preview['preview']['supplier'], 'printify')
        create.assert_not_awaited()
        self.assertEqual(self.post('from-etsy', {'listing_id': '42', 'code': 'ABCDEF'}).status_code, 409)
        data = self.post('from-etsy', {'listing_id': '42', 'code': preview['code']}).json()
        self.assertTrue(data['created']);self.assertEqual(create.await_args.args[0], '100')
        with self.sessions() as db:
            p = db.query(Product).one()
            self.assertEqual((p.printify_product_id, p.printify_twin_id, p.etsy_listing_id), ('storetwin', 'etsyshopprod', '42'))
            self.assertFalse(p.active);self.assertTrue(p.draft)
            self.assertEqual([(v.printify_variant_id, v.cost_usd, v.price_usd) for v in p.variants], [(11, 9.0, 25.0)])
        self.assertEqual(self.post('from-etsy', {'listing_id': '42'}, preview=True).json()['created'], False)
        self.assertIn('category', ' '.join(data['problems']))

    def test_downloads_need_their_file_and_other_physical_listings_need_a_supplier(self):
        self.mock('etsy_listing', AsyncMock(return_value=dict(LISTING, is_digital=True)))
        finder = self.mock('printify_for_listing', AsyncMock(return_value=None))
        code = self.post('from-etsy', {'listing_id': '42'}, preview=True).json()['code']
        data = self.post('from-etsy', {'listing_id': '42', 'code': code}).json()
        finder.assert_not_awaited()
        self.assertIn('download file missing: upload it at /admin/digital/', data['problems'])
        self.mock('etsy_listing', AsyncMock(return_value=dict(LISTING, listing_id='43')))
        self.assertEqual(self.post('from-etsy', {'listing_id': '43'}, preview=True).status_code, 422)
        data = self.post('from-etsy', {'listing_id': '43', 'supplier': 'lulu'}, preview=True).json()
        self.assertEqual(data['preview']['supplier'], 'lulu')

    def add(self, **kw):
        with self.sessions() as db:
            p = Product(slug=kw.pop('slug', 'p'), title='Ratio', description='Hand-drawn spirals.', image_url='https://img/a.jpg',
                        price_usd=24.99, active=True, **kw)
            p.variants = [ProductVariant(name='8x10', printify_variant_id=11, price_usd=24.99, cost_usd=9, active=True)]
            db.add(p);db.commit();return p.id

    def test_printify_product_goes_to_etsy_through_its_twin(self):
        pid = self.add(supplier='printify', printify_product_id='storeprod')
        self.mock('get_printify', AsyncMock(side_effect=[SOURCE, {'external': {'id': '555'}}]))
        create = self.mock('create_twin', AsyncMock(return_value={'id': 'newtwin'}))
        publish = self.mock('publish_twin_to_etsy', AsyncMock())
        preview = self.post(f'to-etsy/{pid}', {}, preview=True).json()
        self.assertEqual(preview['preview']['action'], 'create twin and publish');publish.assert_not_awaited()
        data = self.post(f'to-etsy/{pid}', {'code': preview['code']}).json()
        self.assertEqual(create.await_args.args[0], '200')
        self.assertEqual(create.await_args.args[1]['variants'][0]['price'], 2499)
        publish.assert_awaited_once_with('newtwin')
        self.assertEqual(data['etsy_listing_id'], '555')
        with self.sessions() as db:
            p = db.get(Product, pid);self.assertEqual((p.printify_twin_id, p.etsy_listing_id), ('newtwin', '555'))
        update = self.mock('update_twin', AsyncMock())
        self.mock('get_printify', AsyncMock(return_value=SOURCE))
        code = self.post(f'to-etsy/{pid}', {'price_usd': 29.0}, preview=True).json()['code']
        self.post(f'to-etsy/{pid}', {'price_usd': 29.0, 'code': code})
        self.assertEqual(update.await_args.args[:2], ('200', 'newtwin'))
        self.assertEqual(update.await_args.args[2]['variants'][0]['price'], 2900)

    def test_download_becomes_an_etsy_draft_and_cj_is_refused(self):
        cj = self.add(slug='cj', supplier='cj')
        self.assertEqual(self.post(f'to-etsy/{cj}', {}, preview=True).status_code, 422)
        pid = self.add(slug='pdf', supplier='digital', digital_file='ratio.pdf')
        self.assertEqual(self.post(f'to-etsy/{pid}', {'taxonomy_id': 1}, preview=True).status_code, 409)
        (self.dir / 'ratio.pdf').write_bytes(b'%PDF')
        self.assertEqual(self.post(f'to-etsy/{pid}', {}, preview=True).status_code, 422)
        body = {'taxonomy_id': 2078, 'extra': {'tags': 'math,art'}}
        preview = self.post(f'to-etsy/{pid}', body, preview=True).json()
        fields = preview['preview']['fields']
        self.assertEqual((fields['type'], fields['price'], fields['tags']), ('download', '24.99', 'math,art'))
        draft = self.mock('create_etsy_draft', AsyncMock(return_value='777'))
        self.assertEqual(self.post(f'to-etsy/{pid}', dict(body, extra={'tags': 'other'}, code=preview['code'])).status_code, 409)
        data = self.post(f'to-etsy/{pid}', dict(body, code=preview['code'])).json()
        self.assertEqual((data['etsy_listing_id'], data['state']), ('777', 'draft'))
        self.assertEqual(draft.await_args.args[2].name, 'ratio.pdf')
        self.assertEqual(self.post(f'to-etsy/{pid}', body, preview=True).status_code, 409)

    def test_etsy_listing_is_parsed_into_plain_text_and_variants(self):
        listing = {'listing_id': 42, 'shop_id': 300, 'title': 'Phi &amp; Pi', 'description': 'It&#39;s math',
                   'price': {'amount': 2500, 'divisor': 100, 'currency_code': 'USD'}, 'listing_type': 'physical',
                   'images': [{'rank': 2, 'url_fullxfull': 'b'}, {'rank': 1, 'url_fullxfull': 'a'}]}
        inventory = {'products': [
            {'property_values': [{'values': ['8&quot;x10&quot;']}], 'offerings': [{'price': {'amount': 2500, 'divisor': 100}}]},
            {'is_deleted': True, 'offerings': [{'price': {'amount': 1, 'divisor': 100}}]}]}
        api = self.mock('_etsy', AsyncMock(side_effect=[listing, inventory]))
        import asyncio
        data = asyncio.run(crosslist.etsy_listing('42'))
        self.assertEqual((data['title'], data['description'], data['images']), ('Phi & Pi', "It's math", ['a', 'b']))
        self.assertEqual(data['variants'], [{'name': '8"x10"', 'price_usd': 25.0}])
        self.assertEqual(api.await_args_list[0].args, ('GET', '/application/listings/42?includes=Images'))
        api.side_effect = [dict(listing, shop_id=999)]
        with self.assertRaises(crosslist.CrossListError):
            asyncio.run(crosslist.etsy_listing('42'))

    def test_guards(self):
        self.assertEqual(self.client.post('/api/internal/crosslist/from-etsy', json={'listing_id': '1'}).status_code, 401)
        self.assertEqual(self.client.post('/api/internal/crosslist/from-etsy', json={'listing_id': '1'},
                                          headers={'Authorization': 'Bearer ' + KEY, 'X-Real-IP': '1.2.3.4'}).status_code, 404)
        self.assertEqual(self.post('from-etsy', {'listing_id': 'abc'}).status_code, 422)

if __name__ == '__main__':
    unittest.main()
