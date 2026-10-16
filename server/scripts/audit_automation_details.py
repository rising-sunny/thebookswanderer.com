"""Read-only follow-up for queue, sender, sample exclusion and pin copy."""
import asyncio,json,os,re,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
from email.utils import parseaddr
from dotenv import load_dotenv
ROOT=Path('/var/www/thebookswanderer.com/server');sys.path.insert(0,str(ROOT));load_dotenv(ROOT/'.env')
from database import engine
from services import pinterest as pin,collaborators_store as store

def db(path):
 c=sqlite3.connect(Path(path).absolute().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
def rows(c,s):return [dict(r) for r in c.execute(s)]
def emit(k,v):print(k+' '+json.dumps(v,default=str,ensure_ascii=False),flush=True)

async def main():
 emit('MAIL_SENDER',{'is_hello_at_thebookswanderer_com':parseaddr(os.getenv('MAIL_FROM',''))[1].lower()=='hello@thebookswanderer.com','daily_new_invitation_cap':10})
 with db(engine.url.database) as c:
  emit('PIN_LEDGER',{'total_active_rows':c.execute("SELECT count(*) FROM pinterest_pins WHERE status='active'").fetchone()[0],'distinct_active_pin_ids':c.execute("SELECT count(DISTINCT pin_id) FROM pinterest_pins WHERE status='active' AND pin_id<>''").fetchone()[0],'duplicate_pin_ids':rows(c,"SELECT pin_id,count(*) AS n FROM pinterest_pins WHERE status='active' AND pin_id<>'' GROUP BY pin_id HAVING count(*)>1"),'failed':rows(c,"SELECT product_slug,kind,created_at FROM pinterest_pins WHERE status='failed'")})
  emit('ORDERS',{'status_counts':rows(c,'SELECT status,count(*) AS n FROM orders GROUP BY status'),'reminders_sent':c.execute('SELECT count(*) FROM orders WHERE cart_reminder_sent_at IS NOT NULL').fetchone()[0]})
  selected=rows(c,"SELECT r.pin_id,p.slug,p.supplier FROM pinterest_pins r JOIN products p ON p.slug=r.product_slug WHERE r.status='active' AND p.supplier IN ('printify','lulu') ORDER BY r.id DESC LIMIT 3")
 with db(store.data_dir()/'research.db') as c:
  emit('TEST_EXCLUSION',{'samples':c.execute('SELECT count(*) FROM outreach_samples').fetchone()[0],'sample_addresses_in_campaign':c.execute('SELECT count(*) FROM outreach_deliveries d WHERE EXISTS (SELECT 1 FROM outreach_samples s WHERE s.email=d.email)').fetchone()[0],'currently_uncontacted_sites':c.execute("SELECT count(DISTINCT c.source_id) FROM candidates c WHERE c.status IN ('pending','approved') AND NOT EXISTS (SELECT 1 FROM outreach_deliveries d WHERE d.source_id=c.source_id)").fetchone()[0]})
 for path in sorted(Path('/var/log').glob('tbw*cart*')):
  if path.is_file():
   lines=path.read_text(errors='replace').splitlines();clean=[re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[email]',s)[:300] for s in lines[-6:]]
   emit('CART_LOG',{'file':path.name,'modified_utc':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc),'last_lines':clean})
 for item in selected:
  try:
   p=await pin.api_request('GET','/pins/'+item['pin_id']);desc=p.get('description','')
   emit('PIN_SHIPPING_COPY',{'slug':item['slug'],'supplier':item['supplier'],'pin_id':item['pin_id'],'claims_free_worldwide_shipping':'free worldwide shipping' in desc.lower(),'pin_created_at':p.get('created_at')})
  except Exception as e:emit('PIN_SHIPPING_COPY',{'slug':item['slug'],'error_type':type(e).__name__})
 emit('COMPLETE',{'read_only':True,'emails_sent':False,'published':False})
asyncio.run(main())
