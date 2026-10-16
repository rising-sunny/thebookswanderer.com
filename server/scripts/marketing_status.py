"""Read-only operational summary; no addresses, credentials or message sends."""
import asyncio,json,sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));load_dotenv(ROOT/'.env')
from sqlalchemy import func
from database import SessionLocal
from models import Product,PinterestPin,NewsletterSubscriber
from services import collaborators_store as store,pinterest as pin,monthly_newsletter as monthly

async def main():
 with SessionLocal() as db:
  records=db.query(PinterestPin).filter(PinterestPin.status=='active',PinterestPin.pin_id!='').all()
  active=db.query(Product).filter(Product.active.is_(True)).all();recorded={r.product_slug for r in records}
  pins={'active_records':len(records),'unique_pins':len({r.pin_id for r in records}),'duplicate_history':db.query(PinterestPin).filter_by(status='duplicate').count(),'missing_products':[p.slug for p in active if p.slug not in recorded],'token':pin.token_health()}
  checked=set();copy_errors=[];verified=[]
  products={p.slug:p for p in active}
  for row in records:
   product=products.get(row.product_slug)
   if not product or product.supplier not in ('lulu','printify','digital') or row.pin_id in checked:continue
   checked.add(row.pin_id)
   try:
    live=await pin.api_request('GET','/pins/'+row.pin_id)
    if 'worldwide' in (live.get('description') or '').lower():copy_errors.append(row.pin_id)
    if row.product_slug in ('reading-society-tote','reading-society-notebook'):verified.append({'slug':row.product_slug,'pin_id':row.pin_id})
   except Exception as exc:copy_errors.append({'pin_id':row.pin_id,'error_type':type(exc).__name__})
  pins['shipping_copy_remaining_errors']=copy_errors;pins['backfill_verified']=verified
  newsletter={'active_subscribers':db.query(NewsletterSubscriber).filter_by(active=True).count(),'schedule':monthly.run(send=False)}
 store.init_store()
 with store.connect() as db:
  reader={'sources':db.execute('SELECT count(*) FROM sources').fetchone()[0],'auto_sources':db.execute("SELECT count(*) FROM sources WHERE origin='auto'").fetchone()[0],'candidates':{r[0]:r[1] for r in db.execute('SELECT status,count(*) FROM candidates GROUP BY status')},'deliveries':{r[0]:r[1] for r in db.execute('SELECT status,count(*) FROM outreach_deliveries GROUP BY status')},'last_run':[dict(r) for r in db.execute('SELECT started_at,finished_at,status,sites,found,added,errors FROM runs ORDER BY id DESC LIMIT 1')],'duplicate_emails':len(db.execute('SELECT email FROM outreach_deliveries GROUP BY email HAVING count(*)>1').fetchall()),'sample_invitations':db.execute('SELECT count(*) FROM outreach_deliveries WHERE email IN (SELECT email FROM outreach_samples)').fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='outreach_samples'").fetchone() else 0}
  newsletter['delivery_counts']=[dict(r) for r in db.execute('SELECT period,status,count(*) AS n FROM monthly_deliveries GROUP BY period,status')]
 schedules={}
 for name in ('tbw-reader-outreach','tbw-monthly-newsletter','tbw-social-post'):
  path=Path('/etc/cron.d')/name
  schedules[name]=[' '.join(line.split()[:5]) for line in path.read_text().splitlines() if line and not line.startswith('#')] if path.exists() else None
 print(json.dumps({'pinterest':pins,'reader_campaign':reader,'monthly_newsletter':newsletter,'schedules_utc':schedules},ensure_ascii=False))
asyncio.run(main())
