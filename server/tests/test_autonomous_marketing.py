"""Offline regression tests: provider copy, discovery and once-only mailing."""
import asyncio,json,os,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch,AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base
from models import Product,NewsletterSubscriber,EmailOptOut,PinterestPin
from services import pinterest as pin,pinterest_jobs as jobs,collaborators_store as store,monthly_newsletter as monthly,outreach
import discover_literary_sources as discovery
import repair_marketing_pins as repair

class Fixture(unittest.TestCase):
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
  env=patch.dict(os.environ,{'COLLABORATORS_DATA_DIR':self.folder.name,'SECRET_KEY':'test-key','FREE_SHIPPING':'1','LULU_SHIP_COUNTRIES':'US,GB','SMTP_HOST':'smtp.example','MAIL_FROM':'orders@thebookswanderer.com','SMTP_USER':'test'});env.start();self.addCleanup(env.stop)
  store.init_store()
  self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(self.engine);self.addCleanup(self.engine.dispose)
  self.sessions=sessionmaker(bind=self.engine)
  p=patch.object(monthly,'SessionLocal',self.sessions);p.start();self.addCleanup(p.stop)
  p=patch('database.SessionLocal',self.sessions);p.start();self.addCleanup(p.stop)
  with self.sessions() as db:
   db.add(Product(slug='one-book',title='Book <one>',supplier='lulu',price_usd=22,active=True,image_url='/assets/logo.webp'));db.commit()

class PinterestTests(Fixture):
 def test_restricted_pin_edit_stops_patching_and_prepares_private_copy_plan(self):
  from fastapi import HTTPException
  with self.sessions() as db:
   product=db.query(Product).first()
   db.add_all([PinterestPin(product_slug=product.slug,pin_id='one',status='active'),PinterestPin(product_slug=product.slug,pin_id='two',status='active')]);db.commit()
  calls=[]
  async def api(method,path,**kwargs):
   calls.append((method,path,kwargs))
   if method=='GET':return {'title':'Original variant title','description':'From $22 USD with free worldwide shipping.'}
   raise HTTPException(401,json.dumps({'code':3,'message':'Your application does not have access to this restricted feature: pin_edit'}))
  with patch.object(repair,'init_db'),patch.object(repair,'SessionLocal',self.sessions),patch.object(repair.pin,'api_request',side_effect=api),patch.object(repair.asyncio,'sleep',new=AsyncMock()):
   result=asyncio.run(repair.run(apply=True))
  self.assertEqual(len([c for c in calls if c[0]=='PATCH']),1)
  self.assertEqual(result['editing_blocked']['feature'],'pin_edit');self.assertEqual(result['updated'],0);self.assertEqual(result['pending_descriptions'],2)
  plan=json.loads((Path(self.folder.name)/'pinterest_copy_repairs.json').read_text())
  self.assertEqual(plan['pending'][0]['title'],'Original variant title');self.assertNotIn('worldwide',plan['pending'][0]['description'])
  self.assertIn('USD. Printed',plan['pending'][0]['description'])

 def test_copy_plan_requires_admin_and_stays_private(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from routers.collaborators import router
  (Path(self.folder.name)/'pinterest_copy_repairs.json').write_text(json.dumps({'pending':[{'pin_id':'123','title':'A book','description':'US delivery only'}],'editing_blocked':{'feature':'pin_edit'}}))
  app=FastAPI();app.include_router(router)
  with TestClient(app) as client:
   self.assertEqual(client.get('/admin/pinterest/copy-repairs').status_code,401)
   response=client.get('/admin/pinterest/copy-repairs',headers={'X-Admin-Key':'test-key'})
   self.assertEqual(response.status_code,200);self.assertIn('no-store',response.headers['cache-control']);self.assertIn('noindex',response.headers['x-robots-tag']);self.assertIn('US delivery only',response.text)

 def test_shipping_matches_supplier_and_configured_destinations(self):
  for supplier in ('lulu','printify','digital','cj'):
   payload=pin.product_pin_payload({'slug':'book','title':'Book','supplier':supplier,'price_usd':20})
   self.assertNotIn('worldwide',payload['description'])
   if supplier=='lulu':self.assertIn('GB, US',payload['description']);self.assertNotIn('AU',payload['description'])
   if supplier=='printify':self.assertIn('US delivery only',payload['description'])
   if supplier=='digital':self.assertIn('no physical shipping',payload['description'])
  with patch.dict(os.environ,{'FREE_SHIPPING':'0'}):
   self.assertNotIn('shipping included',pin.shipping_copy({'supplier':'printify'}).lower())

 def test_existing_pin_copy_repair_is_repeatable(self):
  original='A book. From $22 USD with free worldwide shipping. Shop the collection.'
  product={'supplier':'lulu'}
  repaired=repair.corrected_description(original,product)
  self.assertNotIn('worldwide',repaired);self.assertIn('GB, US',repaired)
  self.assertEqual(repair.corrected_description(repaired,product),repaired)

 def test_recording_same_remote_pin_never_inflates_the_count(self):
  with self.sessions() as db:
   p=db.query(Product).first()
   a=jobs._record(db,product=p,board_id='board',pin_id='remote-pin',kind='drip')
   b=jobs._record(db,product=p,board_id='board',pin_id='remote-pin',kind='drip')
   self.assertEqual(a.id,b.id);self.assertEqual(db.query(PinterestPin).count(),1)
   jobs._record(db,product=p,board_id='board',pin_id='',kind='drip',status='failed')
   jobs._record(db,product=p,board_id='board',pin_id='',kind='drip',status='failed')
   self.assertEqual(db.query(PinterestPin).count(),3)

 def test_migration_preserves_duplicate_history_and_prevents_new_duplicates(self):
  import database
  with self.sessions() as db:
   db.add_all([PinterestPin(pin_id='same',status='active'),PinterestPin(pin_id='same',status='active')]);db.commit()
  with patch.object(database,'engine',self.engine),patch('live._ensure_schema'):
   database.init_db();database.init_db()
  with self.sessions() as db:
   self.assertEqual(db.query(PinterestPin).filter_by(status='active').count(),1)
   self.assertEqual(db.query(PinterestPin).filter_by(status='duplicate').count(),1)
   db.add(PinterestPin(pin_id='same',status='active'))
   from sqlalchemy.exc import IntegrityError
   with self.assertRaises(IntegrityError):db.commit()

class DiscoveryTests(Fixture):
 def test_public_blogrolls_and_hosted_blogs_are_followed_but_social_links_are_not(self):
  html='<a href="/blogroll">Blogs amigos</a><a href="https://reader.wordpress.com/">Book reviews</a><a href="https://instagram.com/books">Book reviews</a><a href="http://127.0.0.1/books">Book reviews</a><a rel="nofollow" href="https://otherbook.org/">Book reviews</a>'
  self.assertEqual(discovery.community_pages(html,'https://bookblog.org/'),['https://bookblog.org/blogroll'])
  self.assertEqual(discovery.candidate_links(html,'https://bookblog.org/'),['https://reader.wordpress.com/'])
  self.assertEqual(discovery.community_pages('<meta name="robots" content="nofollow">'+html,'https://bookblog.org/'),[])

 def test_bootstrap_sources_are_verified_and_rotate_between_runs(self):
  class Fetcher:
   def __init__(self,url,**kwargs):pass
   def page(self,url):return url,'<h1>Book reading reviews</h1><p>A blog for readers and authors.</p>'
   def close(self):pass
  with patch.object(discovery,'Fetcher',Fetcher):
   first=discovery.run();second=discovery.run()
  self.assertGreater(first['added'],0);self.assertGreater(second['added'],0)
  with store.connect() as db:
   self.assertEqual(db.execute("SELECT count(*) FROM sources WHERE origin='auto'").fetchone()[0],first['added']+second['added'])

 def test_unavailable_hubs_do_not_become_sources(self):
  class Fetcher:
   def __init__(self,*args,**kwargs):pass
   def page(self,url):raise discovery.ResearchError('robots blocked')
   def close(self):pass
  with patch.object(discovery,'Fetcher',Fetcher):result=discovery.run()
  self.assertEqual(result['added'],0);self.assertGreater(result['unavailable'],0)

class MonthlyTests(Fixture):
 NOW=datetime(2026,11,1,12,tzinfo=timezone.utc)
 def add_sub(self,email,**kw):
  values={'email':email,'active':True,'lang':'en','welcome_step':3,'welcome_at':datetime(2026,10,20),'source':'homepage'};values.update(kw)
  with self.sessions() as db:db.add(NewsletterSubscriber(**values));db.commit()

 def test_sample_suppression_incomplete_welcome_and_non_subscribers_are_excluded(self):
  self.add_sub('reader@example.com');self.add_sub('sample@example.com');self.add_sub('optout@example.com');self.add_sub('new@example.com',welcome_step=1);self.add_sub('test@example.com',source='test-preview')
  with self.sessions() as db:db.add(EmailOptOut(email='optout@example.com'));db.commit()
  with store.connect() as db:
   db.execute('CREATE TABLE outreach_samples(email TEXT)');db.execute("INSERT INTO outreach_samples VALUES('sample@example.com')")
   sid=db.execute("INSERT INTO sources(name,url,lang,category,reason) VALUES('Other','https://bookblog.org','en','Blog','Books')").lastrowid
   store.save_candidate(db,sid,{'email':'professional@example.com','source_url':'https://bookblog.org/contact','evidence':'Public contact','purpose':'Collaboration'})
  with patch.object(monthly.mail,'_send_sync',return_value=True) as send:
   result=monthly.run(send=True,now=self.NOW)
   self.assertEqual(result['counts'],{'sent':1});self.assertEqual(send.call_count,1)
   self.assertEqual(send.call_args.kwargs['to'],['reader@example.com']);self.assertEqual(send.call_args.kwargs['from_address'],'hello@thebookswanderer.com')
  self.assertEqual(outreach.global_contact_state('sample@example.com'),'test_address')
  with store.connect() as db:
   sid=db.execute("INSERT INTO sources(name,url,lang,category,reason) VALUES('Sample','https://samplebook.org','en','Blog','Books')").lastrowid
   store.save_candidate(db,sid,{'email':'sample@example.com','source_url':'https://samplebook.org/contact','evidence':'Public contact','purpose':'Collaboration'})
   sample_id=db.execute("SELECT id FROM candidates WHERE email='sample@example.com'").fetchone()[0]
  self.assertNotIn(sample_id,outreach.auto_candidates())
  self.assertEqual(outreach.prepare('sample-exclusion',outreach.selected_candidates([sample_id])),0)

 def test_one_delivery_per_month_and_uncertain_sends_are_not_retried(self):
  self.add_sub('reader@example.com')
  with patch.object(monthly.mail,'_send_sync',return_value=True) as send:
   monthly.run(send=True,now=self.NOW);monthly.run(send=True,now=self.NOW.replace(day=2));self.assertEqual(send.call_count,1)
   monthly.run(send=True,now=self.NOW.replace(month=12));self.assertEqual(send.call_count,2)
  self.add_sub('second@example.com')
  with patch.object(monthly.mail,'_send_sync',return_value=False) as send:
   result=monthly.run(send=True,now=self.NOW);monthly.run(send=True,now=self.NOW.replace(day=2));self.assertEqual(send.call_count,1);self.assertEqual(result['counts']['uncertain'],1)

 def test_first_issue_and_dry_run_never_send_mail(self):
  self.add_sub('reader@example.com')
  with patch.object(monthly.mail,'_send_sync') as send:
   self.assertEqual(monthly.run(send=True,now=self.NOW.replace(month=10))['status'],'not_due')
   self.assertEqual(monthly.run(now=self.NOW)['new_eligible'],1)
   self.assertEqual(monthly.run(send=True,now=self.NOW.replace(day=4))['status'],'not_due');send.assert_not_called()

 def test_unsubscribe_after_queue_claim_prevents_delivery(self):
  self.add_sub('reader@example.com')
  with patch.object(monthly,'eligible',side_effect=[[{'email':'reader@example.com','lang':'en'}],[{'email':'reader@example.com','lang':'en'}],[]]),patch.object(monthly.mail,'_send_sync') as send:
   result=monthly.run(send=True,now=self.NOW);self.assertEqual(result['counts'],{'suppressed':1});send.assert_not_called()

 def test_bilingual_issue_uses_live_products_and_escapes_titles(self):
  for lang in ('es','en'):
   content=monthly.draft(lang,'2026-11','https://example.com/unsubscribe')
   self.assertIn('Book &lt;one&gt;',content['html']);self.assertIn('https://example.com/unsubscribe',content['html']);self.assertNotIn('worldwide',content['html'])
   if lang=='es':self.assertIn('/es/products/one-book',content['html']);self.assertIn('noviembre',content['subject'])
   else:self.assertIn('November',content['subject'])
if __name__=='__main__':unittest.main()
