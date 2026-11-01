import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

spec=importlib.util.spec_from_file_location('editor',Path(__file__).with_name('editor.py'))
e=importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
REAL_PREPARE=e.prepare_photo
NOW=datetime(2026,11,2,15,tzinfo=timezone.utc)
TOPICS=[{'title':t,'slug':s,'lang':l} for t,s,l in [
 ('Build a thoughtful monthly reading reflection','monthly-reading-reflection','en'),
 ('Cómo organizar tus notas al terminar una novela','notas-al-terminar-novela','es'),
 ('Choose a manageable library reading routine','manageable-library-routine','en'),
 ('Ideas para conversar sobre tus próximas lecturas','conversar-proximas-lecturas','es')]]
def article(title='A practical routine for recording memorable passages'):
 return {'title':title,'description':'A practical guide to choosing a sustainable reading routine and keeping useful notes for your next reading session.',
         'examples':[{'heading':'A concrete example '+str(i),'text':'This is an illustrative reading plan: choose three possible books now, record one finished book and review the next choices later.'+str(i)} for i in range(2)],
         'sections':[{'heading':'Reading section '+str(i), 'paragraphs':[' '.join('word'+str(i*150+j) for j in range(150))], 'sources':['1']} for i in range(4)]}

class Fixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name); self.site=self.root/'site'; self.state=self.root/'state'; self.state.mkdir()
  (self.site/'guides').mkdir(parents=True)
  for folder,title in [('reading-challenge-2027','A yearly reading challenge'),('reto-de-lectura-2027','Un reto de lectura anual')]:
   p=self.site/folder/'index.html'; p.parent.mkdir(); p.write_text('<h1>'+title+'</h1><main>Read at your own pace and write notes.</main>')
  self.report=self.root/'report.json'; self.refresh(NOW)
  self.cfg=dict(enabled=True,model='deepseek-flash',monthly_usd=5,input_usd_per_million=.3,output_usd_per_million=1.2,site_root=str(self.site),report_path=str(self.report))
  (self.state/'deepseek-key').write_text('fixture-not-a-real-key')
  self.env=patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(self.state)}); self.env.start(); self.addCleanup(self.env.stop)
  self.photo_patch=patch.object(e,'prepare_photo',return_value=None); self.photo_patch.start(); self.addCleanup(self.photo_patch.stop)
  self.calls=[]; self.approve=True
  owner=self
  class Fake:
   def __init__(self,*args): pass
   def ask(self,purpose,prompt,limit=4000):
    owner.calls.append(purpose)
    if purpose.endswith(':plan'): return {'topics':copy.deepcopy(TOPICS)}
    if purpose.endswith(':review'): return {'approved':owner.approve,'findings':[] if owner.approve else ['unsupported'],'checks':{k:owner.approve for k in e.REVIEW_CHECKS},'added_value':['A new concrete example offers a usable plan not included in the supplied source material.','A second worked example illustrates how to adjust the plan after changing the reading target.']}
    count=sum(p.endswith(':write') for p in owner.calls)
    result=article(TOPICS[count-1]['title'])
    if TOPICS[count-1]['lang']=='es':
     for section in result['sections']: section['sources']=['2']
    return result
  self.Fake=Fake
 def refresh(self,now):
  self.report.write_text(json.dumps({'generated_at':now.isoformat(),'stale':False,'periods':{'current':{'start':'2026-10-01','end':'2026-10-28','top_queries':[{'query':'reading routine','impressions':5}],'top_pages':[]}}}))
 def run_job(self,now=NOW): return e.run(self.cfg,self.state,now,self.Fake,lambda src:None)
 def test_first_run_publishes_and_second_is_noop(self):
  r=self.run_job(); self.assertEqual(r['status'],'published')
  self.assertEqual(self.run_job()['status'],'already_attempted'); self.assertEqual(len(self.calls),3)
  p=self.site/'guides/editor-monthly-reading-reflection/index.html'
  self.assertIn('rel="canonical"',p.read_text()); self.assertEqual(p.stat().st_mode&0o777,0o644)
  self.assertEqual(p.parent.stat().st_mode&0o777,0o755)
  self.assertIn('editor-monthly-reading-reflection',(self.site/'guides/editor-reading-notes/index.html').read_text())
 def test_four_weeks_reuse_plan_and_stop_at_monthly_cap(self):
  # Use July, which has five Mondays, to test the fifth-run cap without a month rollover.
  start=datetime(2026,7,1,15,tzinfo=timezone.utc)
  for i in range(4):
   date=start+timedelta(days=7*i); self.refresh(date)
   self.assertEqual(self.run_job(date)['status'],'published')
  date=start+timedelta(days=28); self.refresh(date)
  self.assertEqual(self.run_job(date)['status'],'monthly_limit')
  self.assertEqual(len(self.calls),9)
 def test_disabled_makes_no_call(self):
  self.cfg['enabled']=False; self.assertEqual(self.run_job()['status'],'disabled'); self.assertFalse(self.calls)
 def test_stale_report_blocks_generation(self):
  with self.assertRaisesRegex(e.Stop,'report_stale'): self.run_job(NOW+timedelta(days=10))
  self.assertFalse(self.calls)
 def test_future_report_blocks(self):
  self.refresh(NOW+timedelta(days=1))
  with self.assertRaisesRegex(e.Stop,'report_stale'): self.run_job()
 def test_review_rejection_is_private_and_not_retried(self):
  self.approve=False
  with self.assertRaisesRegex(e.Stop,'editorial_review_failed'): self.run_job()
  self.assertEqual(list((self.site/'guides').glob('editor-*')),[])
  self.assertTrue(list(self.state.glob('*-review.json')))
  self.assertEqual(self.run_job()['status'],'already_attempted')
 def test_existing_page_not_overwritten(self):
  path=self.site/'guides/editor-monthly-reading-reflection'; path.mkdir(); (path/'index.html').write_text('original')
  with self.assertRaisesRegex(e.Stop,'existing_path'): self.run_job()
  self.assertEqual((path/'index.html').read_text(),'original')
 def test_recover_publication_after_crash(self):
  real=e.publish
  def crash(*args): real(*args); raise RuntimeError('fixture')
  with patch.object(e,'publish',side_effect=crash):
   with self.assertRaises(e.Stop): self.run_job()
  count=len(self.calls); self.assertEqual(self.run_job()['status'],'already_attempted'); self.assertEqual(len(self.calls),count)
  db=e.connect(self.state); self.assertEqual(db.execute('select status from jobs').fetchone()[0],'published')
 def test_hub_does_not_overwrite_curated_file(self):
  path=self.site/'guides/editor-reading-notes'; path.mkdir(); (path/'index.html').write_text('curated')
  with self.assertRaisesRegex(e.Stop,'existing_hub'): self.run_job()
  self.assertEqual((path/'index.html').read_text(),'curated')
 def test_budget_above_authorization_rejected(self):
  self.cfg['monthly_usd']=10
  with self.assertRaisesRegex(e.Stop,'invalid_budget_or_model'): self.run_job()
 def test_bad_plan_traversal_and_reserved_slug_rejected(self):
  for slug in ['../../secret','reading-notes','UPPERCASE']:
   plan=copy.deepcopy(TOPICS); plan[0]['slug']=slug
   with self.assertRaises(e.Stop): e.validate_plan({'topics':plan},[])
 def test_bad_sources_and_markup_rejected(self):
  src,_=e.sources(self.site)
  for change in ['sources','markup','short']:
   a=article()
   if change=='sources': a['sections'][0]['sources']=['unknown']
   if change=='markup': a['sections'][0]['paragraphs'][0]+='<script>fixture</script>'
   if change=='short': a['sections']=[]
   with self.assertRaises(e.Stop): e.validate_article(a,TOPICS[0],src,[])
 def test_render_escapes_and_no_external_model_links(self):
  a=article(); a['title']='A title with "quotes" & ampersand'
  content=e.render(a,TOPICS[0],e.sources(self.site)[0])
  self.assertIn('&amp;',content); self.assertNotIn('<script>fixture',content)
 def test_script_text_not_sent_as_source(self):
  self.assertEqual(e.plain('Hello<script>PRIVATE</script><style>hidden</style> reader'),'Hello reader')
 def test_unavailable_source_holds_before_publication(self):
  def bad(src): raise e.Stop('source_not_available')
  with self.assertRaisesRegex(e.Stop,'source_not_available'):
   e.run(self.cfg,self.state,NOW,self.Fake,bad)
  self.assertEqual(list((self.site/'guides').glob('editor-*')),[])
 def test_link_checks_reject_foreign_hosts(self):
  with patch.object(e,'build_opener') as opener:
   with self.assertRaisesRegex(e.Stop,'invalid_source_host'): e.check_links([{'url':'https://example.invalid/'}])
   opener.assert_not_called()
 def test_link_failure_sanitized(self):
  with patch.object(e,'build_opener') as opener:
   opener.return_value.open.side_effect=RuntimeError('private fixture detail')
   with self.assertRaisesRegex(e.Stop,'^source_not_available$'): e.check_links([{'url':e.BASE+'/reading-challenge-2027/'}])
 def test_tracking_does_not_treat_missing_page_as_zero(self):
  self.run_job()
  self.run_job()
  data=json.loads((self.state/'performance.json').read_text())
  self.assertEqual(data['articles'][0]['coverage'],'not_in_export_top_pages')
  self.assertIsNone(data['articles'][0]['metrics'])
 def pending_publication(self):
  with patch.object(e,'publish',side_effect=PermissionError('fixture')):
   with self.assertRaisesRegex(e.Stop,'permission_denied'): self.run_job()
 def test_recover_reviewed_artifact_without_new_model_calls(self):
  self.pending_publication(); calls=len(self.calls)
  result=e.recover_publications(self.cfg,self.state,lambda src:None)
  self.assertEqual(len(result['urls']),1); self.assertEqual(len(self.calls),calls)
  self.assertEqual(e.recover_publications(self.cfg,self.state,lambda src:None)['urls'],[])
 def test_recovery_rejects_modified_artifact(self):
  self.pending_publication(); path=self.state/'2026-W45.json'
  # NOW is Monday Nov 2, ISO week 45.
  data=json.loads(path.read_text()); data['article']['title']='Modified artifact with unreviewed content'
  path.write_text(json.dumps(data))
  with self.assertRaisesRegex(e.Stop,'artifact_hash_mismatch'): e.recover_publications(self.cfg,self.state,lambda src:None)
 def test_recovery_rechecks_review(self):
  self.pending_publication(); path=self.state/'2026-W45-review.json'
  path.write_text('{"approved":false,"findings":["fixture"]}')
  with self.assertRaisesRegex(e.Stop,'editorial_review_failed'): e.recover_publications(self.cfg,self.state,lambda src:None)
 def test_unwritable_guides_blocks_before_paid_call(self):
  with patch.object(e.os,'access',return_value=False):
   with self.assertRaisesRegex(e.Stop,'publication_directory_not_writable'): self.run_job()
  self.assertEqual(self.calls,[])
 def test_resources_are_unique_and_in_article_language(self):
  src,_=e.sources(self.site); a=article()
  for section in a['sections']: section['sources']=['1','2']
  output=e.render(a,TOPICS[0],src)
  self.assertEqual(output.count('href="'+src[0]['url']+'"'),1)
  self.assertNotIn('href="'+src[1]['url']+'"',output)
  self.assertNotIn('Notas de lectura</a>',output)
 def test_validation_blocks_cross_language_reference(self):
  src,_=e.sources(self.site); a=article(); a['sections'][0]['sources']=['2']
  with self.assertRaisesRegex(e.Stop,'invalid_sources'): e.validate_article(a,TOPICS[0],src,[])
 def test_worked_examples_required_for_new_articles(self):
  a=article(); a['examples']=[]
  with self.assertRaisesRegex(e.Stop,'missing_worked_examples'): e.validate_article(a,TOPICS[0],e.sources(self.site)[0],[])
 def test_bare_approval_no_longer_passes_editorial_review(self):
  self.assertFalse(e.valid_review({'approved':True,'findings':[]}))
  checks={k:True for k in e.REVIEW_CHECKS}; checks['consistent']=False
  self.assertFalse(e.valid_review({'approved':True,'findings':[],'checks':checks,'added_value':['A concrete new example of reading planning absent from the source.']*2}))
 def old_publication(self):
  manifest=json.loads(Path(e.__file__).with_name('slower-pace-revision.json').read_text())
  old=article(manifest['expected_title']); topic=manifest['topic']; src,_=e.sources(self.site)
  content=e.render(old,topic,src)
  e.publish(self.site,manifest['slug'],content)
  db=e.connect(self.state)
  with db: db.execute('INSERT INTO jobs(week,month,topic,status,slug,hash) VALUES(?,?,?,?,?,?)',('2026-W44','2026-11',json.dumps(topic),'published',manifest['slug'],e.digest(content)))
  return self.site/'guides'/manifest['slug']/'index.html',content
 def test_curated_revision_preserves_url_backup_and_api_budget(self):
  path,before=self.old_publication()
  result=e.apply_slower_pace_revision(self.cfg,self.state,lambda src:None)
  self.assertEqual(result['status'],'revised'); self.assertEqual(self.calls,[])
  output=path.read_text(); self.assertIn('12- or 26-Book',output)
  self.assertEqual(output.count('href="'+e.BASE+'/reading-challenge-2027/"'),1)
  self.assertNotIn('Gifts for Kindle',output); self.assertNotIn('El reto',output)
  self.assertEqual((self.state/'revisions/slower-pace-editorial-v2/before.html').read_text(),before)
  self.assertEqual(e.apply_slower_pace_revision(self.cfg,self.state,lambda src:None)['status'],'already_revised')
 def test_revision_rejects_concurrent_public_edit(self):
  path,_=self.old_publication(); path.write_text(path.read_text()+'new owner edit')
  with self.assertRaisesRegex(e.Stop,'publication_conflict'): e.apply_slower_pace_revision(self.cfg,self.state,lambda src:None)
 def test_revision_can_resume_prepared_write_failure(self):
  path,_=self.old_publication(); real=e.atomic
  def fail(destination,content):
   if destination==path: raise PermissionError('fixture')
   return real(destination,content)
  with patch.object(e,'atomic',side_effect=fail):
   with self.assertRaises(PermissionError): e.apply_slower_pace_revision(self.cfg,self.state,lambda src:None)
  self.assertEqual(e.apply_slower_pace_revision(self.cfg,self.state,lambda src:None)['status'],'revised')
  self.assertEqual(self.calls,[])
 def test_photo_download_uses_curated_cc0_and_records_hash(self):
  response=MagicMock(); response.headers.get_content_type.return_value='image/jpeg'
  response.read.return_value=b'\xff\xd8'+b'fixture'*40+b'\xff\xd9'
  with patch.object(e,'build_opener') as opener:
   opener.return_value.open.return_value.__enter__.return_value=response
   photo=REAL_PREPARE(TOPICS[0],self.state)
  self.assertEqual(photo['license'],'CC0-1.0'); self.assertTrue(photo['real_photo'])
  self.assertEqual(photo['sha256'],e.digest_bytes(Path(photo['cache_path']).read_bytes()))
  output=e.render(article(),TOPICS[0],e.sources(self.site)[0],photo)
  self.assertIn('src="photo.jpg"',output); self.assertIn('CC0 1.0',output); self.assertIn('freestocks.org',output)
 def test_photo_failure_is_optional(self):
  with patch.object(e,'build_opener') as opener:
   opener.return_value.open.side_effect=TimeoutError('fixture')
   self.assertIsNone(REAL_PREPARE(TOPICS[0],self.state))
 def test_no_unrelated_photo_is_downloaded(self):
  with patch.object(e,'build_opener') as opener:
   self.assertIsNone(REAL_PREPARE({'title':'Algebraic topology','slug':'topology-exercises'},self.state))
   opener.assert_not_called()
 def test_remove_notice_preserves_exact_rest_of_page_and_ledger(self):
  path,body=self.old_publication()
  with_notice=body.replace('</article>','<p>Prepared with AI assistance and automated editorial checks.</p></article>')
  path.write_text(with_notice)
  db=e.connect(self.state)
  with db: db.execute('UPDATE jobs SET hash=?',(e.digest(with_notice),))
  self.assertEqual(e.remove_editorial_notice(self.cfg,self.state)['status'],'removed')
  self.assertEqual(path.read_text(),body)
  self.assertEqual(db.execute('SELECT hash FROM jobs').fetchone()[0],e.digest(body))
  self.assertEqual(e.remove_editorial_notice(self.cfg,self.state)['status'],'already_removed')
  self.assertEqual(self.calls,[])
 def test_notice_removal_does_not_undo_prior_article_revision(self):
  path,_=self.old_publication(); e.apply_slower_pace_revision(self.cfg,self.state,lambda src:None)
  text=path.read_text().replace('</article>','<p>Prepared with AI assistance and automated editorial checks.</p></article>')
  path.write_text(text); db=e.connect(self.state)
  with db:
   db.execute('UPDATE jobs SET hash=?',(e.digest(text),))
   db.execute('UPDATE revisions SET new_hash=?',(e.digest(text),))
  e.remove_editorial_notice(self.cfg,self.state)
  final=path.read_text()
  self.assertEqual(e.apply_slower_pace_revision(self.cfg,self.state,lambda src:None)['status'],'already_revised')
  self.assertEqual(path.read_text(),final)
  self.assertEqual(db.execute('SELECT hash FROM jobs').fetchone()[0],e.digest(final))
 def test_notice_removal_respects_untracked_owner_edit(self):
  path,_=self.old_publication(); path.write_text(path.read_text()+'owner edit')
  with self.assertRaisesRegex(e.Stop,'publication_conflict'): e.remove_editorial_notice(self.cfg,self.state)
 def test_api_timeout_reserves_and_does_not_retry(self):
  db=e.connect(self.state); api=e.DeepSeek(self.cfg,db,'2026-11','fixture-not-a-real-key')
  with patch.object(e,'build_opener') as opener:
   opener.return_value.open.side_effect=TimeoutError('MUST NOT PRINT SECRET')
   with self.assertRaisesRegex(e.Stop,'provider_failed'): api.ask('one','Return JSON')
   with self.assertRaisesRegex(e.Stop,'call_already_attempted'): api.ask('one','Return JSON')
   self.assertEqual(opener.return_value.open.call_count,1)
  self.assertEqual(db.execute('select state from calls').fetchone()[0],'ambiguous_or_invalid')
 def test_api_budget_blocks_before_network(self):
  db=e.connect(self.state)
  with db: db.execute('insert into calls(month,purpose,reserved,state) values(?,?,?,?)',('2026-11','old',5,'reserved'))
  with patch.object(e,'build_opener') as opener:
   with self.assertRaisesRegex(e.Stop,'budget_limit'): e.DeepSeek(self.cfg,db,'2026-11','fixture').ask('new','Return JSON')
   opener.assert_not_called()
 def test_api_contract_and_complete_response(self):
  db=e.connect(self.state); data={'choices':[{'finish_reason':'stop','message':{'content':'{"approved":true,"findings":[]}'}}],'usage':{'prompt_tokens':4,'completion_tokens':6}}
  response=MagicMock(); response.read.return_value=json.dumps(data).encode()
  with patch.object(e,'build_opener') as opener:
   opener.return_value.open.return_value.__enter__.return_value=response
   result=e.DeepSeek(self.cfg,db,'2026-11','fixture').ask('new','Return JSON')
   payload=json.loads(opener.return_value.open.call_args.args[0].data)
   self.assertEqual(payload['model'],'deepseek-flash'); self.assertEqual(payload['thinking'],{'type':'disabled'})
   self.assertEqual(payload['response_format'],{'type':'json_object'}); self.assertIs(result['approved'],True)
 def test_api_incomplete_is_not_published(self):
  db=e.connect(self.state); response=MagicMock(); response.read.return_value=b'{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}'
  with patch.object(e,'build_opener') as opener:
   opener.return_value.open.return_value.__enter__.return_value=response
   with self.assertRaisesRegex(e.Stop,'provider_failed'): e.DeepSeek(self.cfg,db,'2026-11','fixture').ask('new','JSON')

if __name__=='__main__': unittest.main()
