"""Offline launch checks: artwork, checkout, supplier routing and once-only POST."""
import asyncio
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

SERVER=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVER));sys.path.insert(0,str(SERVER/'scripts'))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Product,ProductVariant,Order,OrderItem,ProdigiSubmission
from services import prodigi_store as p,prodigi_submission as submission,shipping
import publish_prodigi_phyllotaxis as publication
import httpx

ENV={'PRODIGI_API_KEY':'offline-key','PRODIGI_API_KEY_FILE':'','PRODIGI_ORDERS_ENABLED':'1',
     'PRODIGI_ARTWORK_DIR':str(SERVER/'artwork/prodigi'),'SECRET_KEY':'offline-signing-key'}

class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,ENV);self.env.start();self.addCleanup(self.env.stop)
    async def test_transport_rejects_arbitrary_hosts_redirects_and_disabled_orders(self):
        calls=[]
        def handler(request):calls.append(request);return httpx.Response(302,headers={'location':'https://example.com'})
        for method,path in [('GET','https://example.com'),('DELETE','/orders/ord_1'),('POST','/orders/ord_1/cancel')]:
            with self.assertRaises(p.ProdigiError):await p.request(method,path,transport=httpx.MockTransport(handler))
        with patch.dict(os.environ,{'PRODIGI_ORDERS_ENABLED':'0'}):
            with self.assertRaises(p.ProdigiError):await p.request('POST','/orders',{},transport=httpx.MockTransport(handler))
        self.assertEqual(calls,[])
        with self.assertRaises(p.ProdigiError) as error:await p.request('GET','/products/GLOBAL-FAP-12X16',transport=httpx.MockTransport(handler))
        self.assertEqual(len(calls),1);self.assertNotIn('offline-key',str(error.exception))
    async def test_quote_payload_has_no_artwork_or_customer_and_no_cost_exposure(self):
        product=SimpleNamespace(id=1,supplier='prodigi',slug=p.spec()['slug'],price_usd=44.95)
        response={'outcome':'CreatedWithIssues','issues':[{'errorCode':'destinationCountryCode.UsSalesTaxWarning'}],
                  'quotes':[{'shipmentMethod':'Standard','costSummary':{'totalCost':{'amount':'25.85','currency':'USD'},'shipping':{'amount':'11.85','currency':'USD'}}}]}
        with patch.object(p,'request',AsyncMock(return_value=response)) as call:
            result=await p.shipping([(product,None,1)],'US')
        payload=call.call_args.args[2]
        self.assertEqual(payload,{'destinationCountryCode':'US','currencyCode':'USD','shippingMethod':'Standard',
             'items':[{'sku':'GLOBAL-FAP-12X16','copies':1,'attributes':{'paperType':'EMA','substrateWeight':'200gsm'},'assets':[{'printArea':'default'}]}]})
        self.assertEqual(result['shipping_total'],0)
        self.assertNotIn('supplier_total',result)
        response['quotes'][0]['costSummary']['totalCost']['amount']='50.00'
        with patch.object(p,'request',AsyncMock(return_value=response)):
            with self.assertRaises(p.ProdigiError):await p.shipping([(product,None,1)],'US')
    async def test_non_us_and_unreviewed_mapping_fail_before_request(self):
        product=SimpleNamespace(id=1,supplier='prodigi',slug=p.spec()['slug'],price_usd=44.95)
        with patch.object(p,'request',AsyncMock()) as call:
            with self.assertRaises(p.ProdigiError):await p.shipping([(product,None,1)],'IN')
            product.slug='unreviewed'
            with self.assertRaises(p.ProdigiError):await p.shipping([(product,None,1)],'US')
            call.assert_not_awaited()
    def test_artwork_bytes_dimensions_and_signed_access(self):
        from PIL import Image
        with Image.open(p.asset_path()) as im:self.assertEqual(im.size,(3600,4800));self.assertTrue(im.info['icc_profile'])
        url=p.asset_url('https://thebookswanderer.com')
        token=url.split('?sig=')[1]
        self.assertTrue(p.check_asset_signature(p.spec()['artwork_file'],token))
        self.assertFalse(p.check_asset_signature('../.env',token));self.assertFalse(p.check_asset_signature(p.spec()['artwork_file'],'bad'))
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/p.spec()['artwork_file']).write_bytes(b'changed')
            with patch.dict(os.environ,{'PRODIGI_ARTWORK_DIR':tmp}):self.assertFalse(p.ready())
    async def test_missing_credential_file_never_falls_back(self):
        with patch.dict(os.environ,{'PRODIGI_API_KEY_FILE':'/missing/prodigi-file'}):
            self.assertFalse(p.configured())
            with self.assertRaises(p.ProdigiError):await p.request('GET','/products/GLOBAL-FAP-12X16')

class StoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,ENV);self.env.start();self.addCleanup(self.env.stop)
        self.engine=create_engine('sqlite://');Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine,autoflush=False)();self.addCleanup(self.engine.dispose);self.addCleanup(self.db.close)
        self.product=publication.stage(self.db,p.spec(),publish=True);self.db.commit()
        self.order=Order(status='awaiting_payment',paypal_order_id='OFFLINE-PAYPAL',customer_name='Test Customer',email='test@example.com',shipping_address='1 Test Road',shipping_city='Boston',shipping_province='MA',shipping_zip='02108',shipping_country_code='US')
        self.db.add(self.order);self.db.flush()
        self.item=OrderItem(order_id=self.order.id,product_id=self.product.id,variant_id=self.product.default_variant().id,quantity=1,unit_price=44.95)
        self.db.add(self.item);self.db.flush()
        self.claim=submission.prepare(self.db,self.order,'https://thebookswanderer.com');self.db.commit()
    def remote(self):
        payload=json.loads(self.claim.payload_json)
        return {**payload,'id':'ord_offline_123'}
    def paid(self):self.order.status='paid';self.db.commit()
    def test_snapshot_captures_exact_artwork_and_quantities_before_payment(self):
        data=json.loads(self.claim.payload_json)
        self.assertEqual(data['items'][0]['sku'],'GLOBAL-FAP-12X16')
        self.assertEqual(data['items'][0]['copies'],1)
        self.assertTrue(data['items'][0]['assets'][0]['url'].startswith('https://thebookswanderer.com/api/prodigi/artwork/'))
        self.assertEqual(data['shippingMethod'],'Standard')
        self.assertEqual(len(data['idempotencyKey']),36)
        self.assertEqual(self.claim.state,'prepared')
        self.item.quantity=10;self.db.commit()
        self.assertEqual(json.loads(self.claim.payload_json)['items'][0]['copies'],1)
    async def test_unpaid_order_never_posts(self):
        with patch.object(p,'request',AsyncMock()) as request:
            with self.assertRaises(p.ProdigiError):await submission.submit(self.db,self.order)
            request.assert_not_awaited()
    async def test_paid_submission_is_once_only_and_claim_precedes_post(self):
        self.paid()
        async def respond(*args):
            self.db.refresh(self.claim);self.assertEqual(self.claim.state,'submitting')
            return {'outcome':'Created','order':self.remote()}
        with patch.object(p,'request',AsyncMock(side_effect=respond)) as request:
            self.assertEqual(await submission.submit(self.db,self.order),'ord_offline_123')
            self.assertEqual(await submission.submit(self.db,self.order),'ord_offline_123')
            self.assertEqual(request.await_count,1)
        self.assertEqual(self.claim.state,'submitted')
    async def test_concurrent_callback_cannot_create_a_second_order(self):
        self.paid();entered=asyncio.Event();release=asyncio.Event()
        async def respond(*args):
            entered.set();await release.wait()
            return {'outcome':'Created','order':self.remote()}
        with patch.object(p,'request',AsyncMock(side_effect=respond)) as request:
            first=asyncio.create_task(submission.submit(self.db,self.order))
            await entered.wait()
            with self.assertRaises(p.ProdigiError):await submission.submit(self.db,self.order)
            release.set();self.assertEqual(await first,'ord_offline_123')
            self.assertEqual(request.await_count,1)

    async def test_timeout_is_held_without_second_post(self):
        self.paid()
        with patch.object(p,'request',AsyncMock(side_effect=p.ProdigiError('timeout'))) as request:
            for _ in range(2):
                with self.assertRaises(p.ProdigiError):await submission.submit(self.db,self.order)
            self.assertEqual(request.await_count,1)
        self.assertEqual(self.claim.state,'uncertain');self.assertFalse(self.order.prodigi_order_id)
    async def test_unknown_response_is_held_and_read_only_reconcile_verifies_key_and_lines(self):
        self.paid()
        with patch.object(p,'request',AsyncMock(return_value={'outcome':'Created','order':{}})):
            with self.assertRaises(p.ProdigiError):await submission.submit(self.db,self.order)
        wrong=self.remote();wrong['items'][0]['copies']=2
        with patch.object(p,'request',AsyncMock(return_value={'outcome':'Ok','order':wrong})) as request:
            with self.assertRaises(p.ProdigiError):await submission.reconcile(self.db,self.order,'ord_offline_123')
            self.assertEqual(request.call_args.args[0],'GET')
        with patch.object(p,'request',AsyncMock(return_value={'outcome':'Ok','order':self.remote()})) as request:
            self.assertEqual(await submission.reconcile(self.db,self.order,'ord_offline_123'),'ord_offline_123')
            self.assertEqual(request.call_args.args[0],'GET')
    def test_idempotent_publication_does_not_change_other_product_or_variant_ids(self):
        original=(self.product.id,self.product.default_variant().id)
        other=Product(slug='other',title='Other',supplier='cj',active=True);self.db.add(other);self.db.commit()
        for _ in range(2):
            product=publication.stage(self.db,p.spec(),publish=True);self.db.commit()
            self.assertEqual((product.id,product.default_variant().id),original)
        self.assertEqual(self.db.query(Product).count(),2)
        self.assertTrue(other.active)
        self.assertIn('not an AI image generator',product.description)
    async def test_cart_quote_estimate_and_complete_address(self):
        with patch.object(p,'shipping',AsyncMock(return_value={'supplier':'prodigi','from':'Print on demand','logistic_name':'Prodigi Standard','shipping_total':0.0})):
            estimate=await shipping.quote([(self.product,self.product.default_variant(),1)],'US',{})
            self.assertTrue(estimate['is_estimate'])
            full=await shipping.quote([(self.product,self.product.default_variant(),1)],'US',{'street1':'1 Test Road','city':'Boston','state':'MA','postcode':'02108'})
            self.assertFalse(full['is_estimate']);self.assertEqual(full['grand_total'],44.95)
    async def test_prodigi_fulfilment_is_never_sent_to_cj_and_signed_asset_route_is_protected(self):
        import main
        self.paid()
        with patch.object(main,'_submit_to_cj',AsyncMock()) as cj,patch.object(submission,'submit',AsyncMock()) as art,patch.object(main.email_service,'send_order_fulfillment_started',AsyncMock()):
            await main._fulfil(self.order,self.db)
            cj.assert_not_awaited();art.assert_awaited_once()
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:main.prodigi_artwork('../.env','bad')
        self.assertEqual(error.exception.status_code,404)
        with patch.object(main.paypal_service,'configured',return_value=True),patch.object(main.paypal_service,'create_checkout',AsyncMock()) as checkout:
            with patch.object(p,'ready',return_value=False):
                body=main.CheckoutIn(customer_name='Test',email='test@example.com',shipping_country_code='US',shipping_country='United States',items=[{'product_id':self.product.id,'variant_id':self.product.default_variant().id,'quantity':1}])
                with self.assertRaises(HTTPException):await main.checkout(body,self.db)
            checkout.assert_not_awaited()

    async def test_checkout_freezes_manifest_before_paypal_without_supplier_order(self):
        import main
        async def payment(**kwargs):
            claim=self.db.get(ProdigiSubmission,kwargs['order_id'])
            self.assertIsNotNone(claim)
            self.assertEqual(claim.state,'prepared')
            return ('https://example.com/offline-paypal','OFFLINE-SECOND-PAYPAL')
        body=main.CheckoutIn(customer_name='Test Customer',email='test@example.com',shipping_country='United States',shipping_country_code='US',shipping_address='1 Test Road',shipping_city='Boston',shipping_province='MA',shipping_zip='02108',shipping_total=0,expected_total=44.95,items=[{'product_id':self.product.id,'variant_id':self.product.default_variant().id,'quantity':1}])
        quote={'product_total':44.95,'shipping_total':0,'grand_total':44.95,'is_estimate':False,'logistic_name':'Prodigi Standard'}
        with patch.object(main.paypal_service,'configured',return_value=True),patch.object(main,'shipping_quote',AsyncMock(return_value=quote)),patch.object(main.paypal_service,'create_checkout',AsyncMock(side_effect=payment)),patch.object(p,'request',AsyncMock()) as request:
            result=await main.checkout(body,self.db)
            self.assertEqual(result['grand_total'],44.95)
            request.assert_not_awaited()
    async def test_tracking_partial_shipments_and_missing_mapping_are_not_complete(self):
        import sync_order_tracking as tracking
        products={self.product.id:self.product}
        self.assertFalse(tracking.all_legs_submitted(self.order,[self.item],products))
        leg=tracking.legs_for(self.order,[self.item],products)[0]
        with patch.object(p,'request',AsyncMock()) as request:
            await tracking.check_prodigi(leg)
            self.assertEqual(leg.status,'PROBLEM');request.assert_not_awaited()
        leg.ref='ord_offline_123'
        remote={'status':{'stage':'InProgress'},'shipments':[{'status':'Shipped','tracking':{'number':'123','url':'https://example.com/track'},'carrier':{'name':'UPS'}},{'status':'Processing'}]}
        with patch.object(p,'request',AsyncMock(return_value={'outcome':'Ok','order':remote})):
            await tracking.check_prodigi(leg);self.assertNotEqual(leg.status,'SHIPPED')
            remote['status']['stage']='Complete';remote['shipments'][1]['status']='Shipped'
            await tracking.check_prodigi(leg);self.assertEqual(leg.status,'SHIPPED')

if __name__=='__main__':unittest.main()
