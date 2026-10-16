"""Read-only automation health snapshot. Never publish or send messages."""
import asyncio
import collections
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path('/var/www/thebookswanderer.com/server')
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')
from database import engine
from services import email as mail, pinterest as pin, pinterest_jobs as jobs
from services import collaborators_store as store

SECRET_NAMES = ('SECRET_KEY','SMTP_PASSWORD','SMTP_USER','FB_PAGE_TOKEN','FACEBOOK_PAGE_ACCESS_TOKEN','FACEBOOK_USER_ACCESS_TOKEN','INSTAGRAM_USER_ACCESS_TOKEN','PINTEREST_CLIENT_SECRET','META_CAPI_TOKEN')
def safe(value):
    value = str(value)
    for name in SECRET_NAMES:
        secret = os.getenv(name, '')
        if secret: value = value.replace(secret, '[redacted]')
    value = re.sub(r'(?i)((?:access_token|refresh_token|admin_key|client_secret|password)=)[^&\s"\']+',r'\1[redacted]', value)
    return re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email]', value)
def emit(label, data):
    print(label + ' ' + safe(json.dumps(data, default=str, ensure_ascii=False)), flush=True)
def ro(path):
    db = sqlite3.connect(Path(path).absolute().as_uri()+'?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    return db
def rows(db, sql):
    return [dict(row) for row in db.execute(sql)]

def local_state():
    now=datetime.now(timezone.utc)
    emit('TIME',{'utc':now.isoformat(),'social_enabled':os.getenv('SOCIAL_POST_ENABLED','1')!='0','ffmpeg':subprocess.run(['sh','-c','command -v ffmpeg'],capture_output=True,text=True).returncode==0})
    state_path=Path(os.getenv('SOCIAL_POST_STATE',str(ROOT/'data/social_posts.json')))
    state=json.loads(state_path.read_text()) if state_path.exists() else []
    counts={name:sum(bool(entry.get(name)) for entry in state) for name in ['facebook','instagram']}
    emit('SOCIAL_STATE',{'entries':len(state),'success_counts':counts,'distinct_products':len({e.get('slug') for e in state}),'last_entries':state[-10:]})
    for path in sorted(Path('/var/log').glob('tbw*.log')):
        if not any(word in path.name for word in ('social','welcome','pinterest','tracking','outreach')):continue
        try:
            lines=path.read_text(errors='replace').splitlines()
            emit('LOG',{'file':path.name,'modified':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc),'last_lines':[safe(line)[:600] for line in lines[-25:]],'recent_error_lines':[safe(line)[:600] for line in lines[-500:] if re.search('FAILED|Traceback|Exception|Error|error|refused|expired',line)][-12:]})
        except OSError as exc:emit('LOG',{'file':path.name,'error_type':type(exc).__name__})
    emit('PINTEREST_CONFIG',{'enabled':jobs.auto_pin_enabled(),'launch':jobs.launch_pin_enabled(),'per_day':jobs.pins_per_day(),'cooldown_days':jobs.repin_cooldown_days(),'token_health':pin.token_health()})
    with ro(engine.url.database) as db:
        emit('PINS_DB',{'counts':rows(db,'SELECT kind,status,count(*) AS n FROM pinterest_pins GROUP BY kind,status'),'by_day':rows(db,"SELECT date(created_at) AS day,status,count(*) AS n FROM pinterest_pins GROUP BY day,status ORDER BY day DESC LIMIT 14"),'latest':rows(db,'SELECT product_slug,pin_id,kind,status,error,created_at FROM pinterest_pins ORDER BY id DESC LIMIT 16'),'active_products':db.execute('SELECT count(*) FROM products WHERE active=1').fetchone()[0],'active_without_recorded_pin':rows(db,"SELECT p.slug FROM products p WHERE p.active=1 AND NOT EXISTS (SELECT 1 FROM pinterest_pins r WHERE r.product_slug=p.slug AND r.status='active')")})
        emit('NEWSLETTER',{'groups':rows(db,'SELECT active,welcome_step,lang,count(*) AS n FROM newsletter_subscribers GROUP BY active,welcome_step,lang'),'last_signup':rows(db,'SELECT max(created_at) AS last FROM newsletter_subscribers'),'last_welcome':rows(db,'SELECT max(welcome_at) AS last FROM newsletter_subscribers'),'opt_out_count':db.execute('SELECT count(*) FROM email_opt_outs').fetchone()[0],'active_pending_first':db.execute('SELECT count(*) FROM newsletter_subscribers WHERE active=1 AND welcome_step=0').fetchone()[0]})
    with ro(store.data_dir()/'research.db') as db:
        emit('OUTREACH',{'sources':rows(db,'SELECT origin,active,count(*) AS n FROM sources GROUP BY origin,active'),'source_status':rows(db,'SELECT id,name,lang,checked_at,discovery_checked_at,last_status FROM sources ORDER BY id'),'counts':rows(db,'SELECT status,count(*) AS n FROM outreach_deliveries GROUP BY status'),'by_day':rows(db,'SELECT substr(sent_at,1,10) AS day,lang,count(*) AS n FROM outreach_deliveries WHERE sent_at IS NOT NULL GROUP BY day,lang ORDER BY day DESC'),'duplicate_emails':rows(db,'SELECT count(*) AS n FROM outreach_deliveries GROUP BY email HAVING count(*)>1'),'duplicate_sites':rows(db,'SELECT count(*) AS n FROM outreach_deliveries GROUP BY site_key HAVING count(*)>1'),'suppressions':db.execute('SELECT count(*) FROM outreach_suppressions').fetchone()[0],'sample_rows_excluded':db.execute("SELECT count(*) FROM sqlite_master WHERE name='outreach_samples'").fetchone()[0],'campaigns':rows(db,'SELECT id,created_at,last_run_at FROM outreach_campaigns')})
    return state

async def pinterest_read():
    try:
        boards=(await pin.list_boards()).get('items',[])
        emit('PINTEREST_BOARDS',[{key:b.get(key) for key in ['id','name','pin_count','privacy']} for b in boards])
        for board in boards:
            data=await pin.api_request('GET',f"/boards/{board['id']}/pins",params={'page_size':10})
            emit('PINTEREST_RECENT',{'board':board.get('name'),'pins':[{key:p.get(key) for key in ['id','created_at','title','link']} for p in data.get('items',[])]})
    except Exception as exc:
        emit('PINTEREST_API_ERROR',{'type':type(exc).__name__,'detail':safe(getattr(exc,'detail',''))[:400]})

def meta_read(state):
    token=os.getenv('FB_PAGE_TOKEN','');page=os.getenv('FB_PAGE_ID','')
    emit('META_CONFIG',{'page_id':page,'token_configured':bool(token)})
    if not token or not page:return
    with httpx.Client(timeout=30,headers={'Authorization':f'Bearer {token}'}) as client:
        def get(path,fields,limit=None):
            params={'fields':fields}
            if limit:params['limit']=limit
            response=client.get('https://graph.facebook.com/v21.0/'+path,params=params)
            data=response.json()
            if response.status_code>=400:
                error=data.get('error',{})
                return {'http_status':response.status_code,'error_code':error.get('code'),'subcode':error.get('error_subcode'),'message':safe(error.get('message',''))[:400]}
            return data
        page_data=get(page,'id,name,instagram_business_account{id,username}')
        emit('META_PAGE',page_data)
        fb=get(page+'/videos','id,created_time,permalink_url,status',8)
        emit('FACEBOOK_RECENT',fb.get('data',fb))
        ig=(page_data.get('instagram_business_account') or {}).get('id')
        if ig:
            recent=get(ig+'/media','id,media_type,media_product_type,permalink,timestamp',8)
            emit('INSTAGRAM_RECENT',recent.get('data',recent))
        for item in state[-2:]:
            if item.get('facebook'):emit('FACEBOOK_LOG_VERIFY',get(str(item['facebook']),'id,created_time,permalink_url,status'))
            if item.get('instagram'):emit('INSTAGRAM_LOG_VERIFY',get(str(item['instagram']),'id,media_type,media_product_type,permalink,timestamp'))

def smtp_read():
    try:
        from scripts.check_integrations import smtp
        emit('SMTP',smtp())
    except Exception as exc:
        emit('SMTP',{'status':'FAIL','error_type':type(exc).__name__,'smtp_code':getattr(exc,'smtp_code',None)})
    emit('MAIL_CONFIG',{'configured':mail.configured(),'sender':os.getenv('MAIL_FROM','').split('<')[0].strip(),'daily_outreach_limit':os.getenv('OUTREACH_DAILY_LIMIT','20'),'auto_limit':os.getenv('OUTREACH_AUTO_LIMIT','20'),'WELCOME_DELAYS_DAYS':mail.WELCOME_DELAYS_DAYS})

state=local_state()
meta_read(state)
asyncio.run(pinterest_read())
smtp_read()
emit('COMPLETE',{'read_only':True,'published':False,'emails_sent':False})
