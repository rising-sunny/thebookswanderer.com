"""Offline tests. All supplier APIs and payment calls are mocked."""
import asyncio
import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Order, LuluSubmission, Product, OrderItem
from services import lulu, lulu_submission as submit
import sync_order_tracking as tracking

LINES=[{'external_id':'tbw-1-1','title':'Book EN','quantity':2,'pod_package_id':'package-en','interior_url':'https://example.invalid/interior?sig=test','cover_url':'https://example.invalid/cover?sig=test'},
       {'external_id':'tbw-1-2','title':'Book ES','quantity':1,'pod_package_id':'package-es','interior_url':'https://example.invalid/interior-es?sig=test','cover_url':'https://example.invalid/cover-es?sig=test'}]
JOB={'id':73,'external_id':'tbw-1','line_items':[{'external_id':ln['external_id'],'quantity':ln['quantity']} for ln in LINES]}
EMPTY={'results':[],'next':None}

class Submissions(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.engine=create_engine('sqlite:///'+str(Path(self.temp.name)/'test.db'));self.addCleanup(self.engine.dispose);Base.metadata.create_all(self.engine)
  self.sessions=sessionmaker(bind=self.engine);self.db=self.sessions();self.addCleanup(self.db.close)
  self.order=Order(status='paid');self.db.add(self.order);self.db.commit();self.assertEqual(self.order.id,1)
  self.lookup=patch.object(lulu,'request',AsyncMock(return_value=copy.deepcopy(EMPTY)));self.read=self.lookup.start();self.addCleanup(self.lookup.stop)
  self.creation=patch.object(lulu,'create_print_job',AsyncMock(return_value=copy.deepcopy(JOB)));self.create=self.creation.start();self.addCleanup(self.creation.stop)
 def run_submit(self):return asyncio.run(submit.submit(self.db,self.order,copy.deepcopy(LINES),{'name':'Unit Test'}))
 def test_repeat_does_not_recreate_and_preserves_all_lines(self):
  self.assertEqual(self.run_submit(),'73');self.assertEqual(self.run_submit(),'73');self.create.assert_awaited_once();self.assertEqual(self.create.await_args.args[1],LINES)
  self.assertEqual(self.db.get(LuluSubmission,1).state,'submitted')
 def test_preexisting_exact_job_is_adopted(self):
  self.read.return_value={'results':[JOB],'next':None};self.assertEqual(self.run_submit(),'73');self.create.assert_not_awaited()
 def test_readonly_reconciliation_never_creates_and_apply_only_restores_mapping(self):
  self.read.return_value={'results':[JOB],'next':None}
  self.assertTrue(asyncio.run(submit.reconcile(self.db,self.order,LINES)))
  self.assertEqual(self.order.lulu_job_id,'');self.assertIsNone(self.db.get(LuluSubmission,1))
  self.assertTrue(asyncio.run(submit.reconcile(self.db,self.order,LINES,apply=True)))
  self.assertEqual(self.order.lulu_job_id,'73');self.create.assert_not_awaited()
 def test_wrong_remote_print_package_is_not_adopted(self):
  job=copy.deepcopy(JOB);job['line_items'][0]['printable_normalization']={'pod_package_id':'wrong-package'}
  self.read.return_value={'results':[job],'next':None}
  with self.assertRaises(submit.Pending):self.run_submit()
  self.create.assert_not_awaited()
 def test_lost_post_response_is_reconciled_without_a_second_post(self):
  self.create.side_effect=TimeoutError('private response is not logged')
  with self.assertRaises(submit.Pending):self.run_submit()
  self.assertEqual(self.db.get(LuluSubmission,1).state,'uncertain')
  self.read.return_value={'results':[JOB],'next':None};self.assertEqual(self.run_submit(),'73');self.create.assert_awaited_once()
 def test_uncertain_creation_with_no_remote_match_is_held(self):
  self.create.return_value={}
  with self.assertRaises(submit.Pending):self.run_submit()
  with self.assertRaises(submit.Pending):self.run_submit()
  self.create.assert_awaited_once();self.assertEqual(self.order.lulu_job_id,'')
 def test_commit_failure_after_acceptance_is_recoverable(self):
  commit=self.db.commit;calls=0
  def fail_once():
   nonlocal calls
   calls+=1
   if calls==3:raise RuntimeError('simulated DB failure after POST')
   return commit()
  with patch.object(self.db,'commit',side_effect=fail_once):
   with self.assertRaises(submit.Pending):self.run_submit()
  self.read.return_value={'results':[JOB],'next':None};self.assertEqual(self.run_submit(),'73');self.create.assert_awaited_once()
 def test_lookup_failure_before_post_can_be_retried(self):
  self.read.side_effect=TimeoutError()
  with self.assertRaises(TimeoutError):self.run_submit()
  self.create.assert_not_awaited();self.assertEqual(self.db.get(LuluSubmission,1).state,'retryable')
  self.read.side_effect=None;self.assertEqual(self.run_submit(),'73');self.create.assert_awaited_once()
 def test_concurrent_call_has_no_creation_right(self):
  async def exercise():
   entered=asyncio.Event();release=asyncio.Event();calls=0
   async def lookup(*args):
    nonlocal calls
    calls+=1
    if calls==1:entered.set();await release.wait()
    return copy.deepcopy(EMPTY)
   self.read.side_effect=lookup
   first=asyncio.create_task(submit.submit(self.db,self.order,LINES,{}));await entered.wait()
   with self.sessions() as other:
    with self.assertRaises(submit.Pending):await submit.submit(other,other.get(Order,1),LINES,{})
   release.set();await first
  asyncio.run(exercise());self.create.assert_awaited_once()
 def test_partial_external_match_and_pagination_do_not_duplicate(self):
  other=copy.deepcopy(JOB);other['id']=99;other['external_id']='tbw-10'
  self.read.side_effect=[{'results':[other],'next':'https://untrusted.invalid/never-follow'}, {'results':[JOB],'next':None}]
  self.assertEqual(self.run_submit(),'73');self.create.assert_not_awaited()
  self.assertIn('page=2',self.read.await_args.args[1]);self.assertNotIn('untrusted',self.read.await_args.args[1])
 def test_duplicate_remote_jobs_or_different_quantities_require_review(self):
  for jobs in ([JOB,dict(JOB,id=74)],[dict(JOB,line_items=[{'external_id':'tbw-1-1','quantity':999}])]):
   self.read.return_value={'results':jobs,'next':None}
   with self.assertRaises(submit.Pending):self.run_submit()
  self.create.assert_not_awaited()
 def test_interrupted_pre_post_claim_cannot_be_stolen(self):
  self.db.add(LuluSubmission(order_id=1,state='checking'));self.db.commit()
  with self.assertRaises(submit.Pending):self.run_submit()
  self.create.assert_not_awaited()

class AddressesAndTracking(unittest.TestCase):
 def address(self,phone='',name='Unit Test',street2=''):
  return lulu.address(name,'10 Example Street',street2,'Example','NY','US','10001',phone)
 def test_real_fallback_is_used_only_when_buyer_omits_phone(self):
  with patch.dict(os.environ,{'LULU_MERCHANT_PHONE':'+1 202 555 0111'}):
   self.assertEqual(self.address()['phone_number'],'+12025550111')
   self.assertEqual(self.address('+1 202 555 0123')['phone_number'],'+12025550123')
   with self.assertRaises(lulu.LuluError):self.address('abc')
 def test_missing_or_dummy_fields_are_not_fabricated_or_exposed(self):
  with patch.dict(os.environ,{'LULU_MERCHANT_PHONE':''}):
   for phone in ('','0000000000','+11111111'):
    with self.assertRaises(lulu.LuluError):self.address(phone)
   with self.assertRaises(lulu.LuluError):self.address('+12025550111',name=' ')
   secret_street='a customer address that exceeds the allowed second line'
   with self.assertRaises(lulu.LuluError) as error:self.address('+12025550111',street2=secret_street)
   self.assertNotIn(secret_street,str(error.exception))
 def test_unpaid_is_expected_manual_payment_waiting(self):
  leg=tracking.Leg('lulu','73')
  with patch.object(lulu,'request',AsyncMock(return_value={'status':{'name':'UNPAID'},'line_items':[]})):
   asyncio.run(tracking.check_lulu(leg))
  self.assertEqual(leg.status,'WAITING');self.assertIn('manually',leg.help);self.assertNotIn('Add or fix',leg.help)
 def test_mixed_order_requires_every_supplier_and_warehouse_leg(self):
  products={1:SimpleNamespace(supplier='cj',from_country='CN'),2:SimpleNamespace(supplier='cj',from_country='US'),3:SimpleNamespace(supplier='lulu'),4:SimpleNamespace(supplier='printify')}
  items=[SimpleNamespace(product_id=i) for i in products]
  order=SimpleNamespace(cj_order_id='CN:one',lulu_job_id='',printify_order_id='pod')
  self.assertFalse(tracking.all_legs_submitted(order,items,products));order.lulu_job_id='book';self.assertFalse(tracking.all_legs_submitted(order,items,products));order.cj_order_id='CN:one,US:two';self.assertTrue(tracking.all_legs_submitted(order,items,products))
 def test_checkout_rejects_missing_phone_before_paypal_creation(self):
  import main
  body=SimpleNamespace(items=[],customer_name='Unit Test',phone='',shipping_address='10 Example Street',shipping_address2='',shipping_city='Example',shipping_province='NY',shipping_country_code='US',shipping_zip='10001')
  product=SimpleNamespace(supplier='lulu',price_usd=25,slug='book',title='Book')
  with patch.dict(os.environ,{'LULU_MERCHANT_PHONE':''}),patch.object(main.paypal_service,'configured',return_value=True),patch.object(lulu,'configured',return_value=True),patch.object(main,'_load_cart_lines',return_value=[(product,None,1)]),patch.object(main,'_lulu_files',return_value=('interior','cover')),patch.object(main.paypal_service,'create_checkout',AsyncMock()) as create:
   with self.assertRaises(main.HTTPException) as error:asyncio.run(main.checkout(body,SimpleNamespace()))
   self.assertEqual(error.exception.status_code,422);create.assert_not_awaited()

if __name__=='__main__':unittest.main()
