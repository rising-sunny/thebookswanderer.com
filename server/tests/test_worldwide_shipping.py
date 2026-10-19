"""Delivery availability, money totals and payment guards; all providers mocked."""
import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from services import shipping, printify, lulu
from database import Base, get_db
from models import Product, ProductVariant, Order
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ADDR = {'street1':'India Gate','city':'New Delhi','state':'DL','postcode':'110001','phone_number':'+919000000000'}

def item(supplier='printify', price=27.99, origin='US'):
    return (Obj(supplier=supplier, title='A reading accessory', slug='accessory', price_usd=price, from_country=origin,
                printify_product_id='supplier-product',cj_vid='default', lulu_package='package'),
            Obj(price_usd=price, printify_variant_id=123, cj_vid='variant'), 1)

class Quotes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        shipping._cache.clear()
        p=patch.dict(os.environ, {'SHIPPING_MARKUP':'1.15','LULU_MERCHANT_PHONE':'+12025550100'})
        p.start();self.addCleanup(p.stop)

    async def test_printify_india_charges_only_additional_delivery(self):
        async def rate(lines,country,address=None):return 5.35 if country=='US' else 10.39
        with patch.object(printify,'shipping_cost',side_effect=rate):
            r=await shipping.quote([item()], 'IN', ADDR)
        self.assertEqual((r['shipping_total'],r['grand_total']), (5.8,33.79))
        self.assertFalse(r['is_estimate']);self.assertIn('Import duties',r['import_charges_notice'])

    async def test_us_stays_included_and_other_markets_arent_assumed_free(self):
        with patch.object(printify,'shipping_cost',AsyncMock(return_value=10)) as rate:
            us=await shipping.quote([item()], 'US', ADDR)
            self.assertEqual(us['shipping_total'],0)
            rate.assert_awaited_once()
        with patch.object(printify,'shipping_cost',AsyncMock(return_value=10)):
            paid=await shipping.quote([item()], 'KE', ADDR,free_us=False)
            self.assertEqual(paid['shipping_total'],11.5)

    async def test_missing_standard_or_negative_rate_cannot_turn_into_free_shipping(self):
        for response in ({'express':900},{'standard':-1},{'standard':'nan'}):
            with self.subTest(response=response),patch.object(printify,'_request',AsyncMock(return_value=response)):
                with self.assertRaises((printify.PrintifyError,shipping.QuoteError)):
                    await shipping.quote([item()], 'IN', ADDR)

    async def test_cj_unavailable_cart_identifies_item_and_never_uses_zero_rate(self):
        with patch.object(shipping.cj,'freight_calculate',AsyncMock(return_value=[])):
            with self.assertRaises(shipping.QuoteError) as error:
                await shipping.quote([item('cj',origin='US')], 'IN', ADDR)
        self.assertEqual(error.exception.reason,'no_route')
        self.assertEqual(error.exception.products,['A reading accessory'])

    async def test_provider_failure_is_not_permanent_country_exclusion(self):
        with patch.object(shipping.cj,'freight_calculate',AsyncMock(side_effect=shipping.cj.CJError('temporarily down'))):
            with self.assertRaises(shipping.QuoteError) as error:
                await shipping.quote([item('cj')], 'IN', ADDR)
        self.assertEqual((error.exception.status,error.exception.reason),(503,'temporarily_unavailable'))

    async def test_lulu_fallback_method_and_tax_inclusive_final_cost(self):
        async def api(method,path,json=None):
            country=json['shipping_address'].get('country') or json['shipping_address'].get('country_code')
            if path=='/shipping-options/':
                return [{'level':'GROUND','cost_excl_tax':'8','total_days_min':7,'total_days_max':12}]
            return {'total_cost_incl_tax':'13.19' if country=='US' else '14.43'}
        with patch.object(shipping,'lulu_line',return_value={'page_count':160,'quantity':1,'pod_package_id':'package'}),patch.object(lulu,'request',side_effect=api):
            r=await shipping.quote([item('lulu',price=24.99)],'IN',ADDR)
        self.assertEqual(r['grand_total'],26.42)
        self.assertEqual(r['logistic_name'],'Lulu GROUND')
        self.assertEqual(r['legs'][0]['shipping_level'],'GROUND')

    async def test_partial_address_is_an_estimate_and_digital_needs_no_delivery(self):
        with patch.object(printify,'shipping_cost',AsyncMock(return_value=10)):
            r=await shipping.quote([item()], 'IN', {})
            self.assertTrue(r['is_estimate'])
        r=await shipping.quote([item('digital',price=8.99)], 'IN', {})
        self.assertFalse(r['is_estimate']);self.assertEqual(r['grand_total'],8.99)
        self.assertTrue(r['digital_only'])

    async def test_mixed_suppliers_have_one_exact_total(self):
        async def rate(lines,country,address=None):return 5 if country=='US' else 10
        async def freight(**args):return [{'logisticName':'Standard','logisticPrice':5 if args['end_country']=='US' else 7,'logisticAging':'8-12'}]
        with patch.object(printify,'shipping_cost',side_effect=rate),patch.object(shipping.cj,'freight_calculate',side_effect=freight):
            r=await shipping.quote([item(),item('cj',price=12,origin='CN')],'IN',ADDR)
        self.assertEqual((r['product_total'],r['shipping_total'],r['grand_total']),(39.99,8.05,48.04))
        self.assertEqual(len(r['legs']),2)

    async def test_lulu_fulfilment_keeps_quoted_shipping_level(self):
        with patch.object(lulu,'request',AsyncMock(return_value={'id':1})) as api:
            await lulu.create_print_job('test',[],{},shipping_level='GROUND')
        self.assertEqual(api.await_args.args[2]['shipping_level'],'GROUND')

class Checkout(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine);self.addCleanup(self.engine.dispose)
        with self.sessions() as db:
            p=Product(slug='tote',title='Tote',supplier='printify',printify_product_id='supplier-product',price_usd=27.99,active=True)
            p.variants=[ProductVariant(name='One',price_usd=27.99,printify_variant_id=123,active=True)]
            db.add(p);db.commit();self.pid=p.id;self.vid=p.variants[0].id
        def database():
            with self.sessions() as db:yield db
        main.app.dependency_overrides[get_db]=database
        self.addCleanup(main.app.dependency_overrides.clear)
        self.client=TestClient(main.app);self.addCleanup(self.client.close)
        self.create=AsyncMock(return_value=('https://example.invalid/pay','MOCK-PAYPAL'))
        for p in [patch.object(main.paypal_service,'configured',return_value=True),patch.object(main.paypal_service,'create_checkout',self.create)]:
            p.start();self.addCleanup(p.stop)
        self.body={'email':'unit@example.com','customer_name':'Unit Test','shipping_address':'India Gate','shipping_city':'New Delhi','shipping_province':'DL','shipping_country_code':'IN','shipping_country':'India','shipping_zip':'110001','shipping_total':5.8,'expected_total':33.79,'items':[{'product_id':self.pid,'variant_id':self.vid,'quantity':1}]}
        shipping._cache.clear()
    def test_global_selector_includes_previous_unlisted_markets(self):
        codes={d['code'] for d in self.client.get('/api/shipping/destinations').json()['destinations']}
        self.assertTrue({'IN','KE','ZA','PK','XK'}.issubset(codes));self.assertEqual(len(codes),250)
    def test_new_country_is_not_blocked_by_printify_whitelist(self):
        with patch.object(printify,'shipping_cost',AsyncMock(side_effect=[10.39,5.35])):
            r=self.client.get(f'/api/products/{self.pid}/shipping?country_code=IN')
        self.assertTrue(r.json()['available']);self.assertEqual(r.json()['grand_total'],33.79)
        self.assertTrue(r.json()['is_estimate'])
    def test_changed_total_is_rejected_before_any_paypal_order(self):
        for update in ({'shipping_total':0},{'expected_total':27.99},{'expected_total':None}):
            shipping._cache.clear()
            with patch.object(printify,'shipping_cost',AsyncMock(side_effect=[10.39,5.35])):
                r=self.client.post('/api/checkout',json={**self.body,**update})
            self.assertEqual(r.status_code,409)
        self.create.assert_not_awaited()
        with self.sessions() as db:self.assertEqual(db.query(Order).count(),0)
    def test_confirmed_total_is_the_only_amount_sent_to_paypal(self):
        with patch.object(printify,'shipping_cost',AsyncMock(side_effect=[10.39,5.35])):
            r=self.client.post('/api/checkout',json=self.body)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.create.await_args.kwargs['amount_usd'],33.79)
        with self.sessions() as db:self.assertEqual(db.query(Order).one().grand_total,33.79)
    def test_provider_error_blocks_payment_and_names_the_shipping_problem(self):
        with patch.object(printify,'shipping_cost',AsyncMock(side_effect=printify.PrintifyError('No shipping available',{}))):
            r=self.client.post('/api/checkout',json=self.body)
        self.assertEqual(r.status_code,400)
        self.assertEqual(r.json()['detail']['unavailable_products'],['Tote'])
        self.create.assert_not_awaited()

if __name__=='__main__':unittest.main()
