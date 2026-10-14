"""Aggregate-only, read-only audit of organic acquisition infrastructure."""
import json,os,sqlite3,sys,subprocess,tempfile,re
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import defaultdict
from urllib.parse import urlsplit
from dotenv import load_dotenv

ROOT=Path('/var/www/thebookswanderer.com/server')
load_dotenv(ROOT/'.env');sys.path.insert(0,str(ROOT))
NOW=datetime.now(timezone.utc);CUTOFF=(NOW-timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

def main():
    report={'checked_utc':NOW.isoformat(),'window_days':30,'writes_or_sends_performed':False}
    database_url=os.getenv('DATABASE_URL','sqlite:///'+str(ROOT/'data/store.db'))
    if not database_url.startswith('sqlite:///'):raise ValueError('Audit supports the documented SQLite store only')
    database_path=Path(database_url[len('sqlite:///'):])
    db=sqlite3.connect(database_path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    def rows(query,args=()):return [dict(r) for r in db.execute(query,args)]
    tables={r['name'] for r in rows("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'live_events' in tables:
        human="coalesce(ua_class,'') NOT IN ('bot','datacenter','meta','meta-cloud','self')"
        report['tracking_dates']=rows('SELECT min(ts) earliest,max(ts) latest,count(*) events FROM live_events')[0]
        report['ua_classes']=rows('SELECT ua_class,count(*) events FROM live_events WHERE ts>=? GROUP BY ua_class',(CUTOFF,))
        report['tracked_pageviews']=rows(f"SELECT count(*) pageviews,count(DISTINCT session_id) sessions FROM live_events WHERE event_type='pageview' AND ts>=? AND {human}",(CUTOFF,))[0]
        report['source_rows']=rows(f"SELECT coalesce(source,'') source,coalesce(referrer_domain,'') referrer,coalesce(medium,'') medium,coalesce(campaign,'') campaign,count(*) pageviews,count(DISTINCT session_id) sessions FROM live_events WHERE event_type='pageview' AND ts>=? AND {human} GROUP BY source,referrer_domain,medium,campaign ORDER BY sessions DESC LIMIT 60",(CUTOFF,))
        report['funnel_events']=rows(f"SELECT event_type,count(*) events,count(DISTINCT session_id) sessions FROM live_events WHERE ts>=? AND {human} GROUP BY event_type",(CUTOFF,))
        events=rows(f"SELECT path,count(*) pageviews,count(DISTINCT session_id) sessions FROM live_events WHERE ts>=? AND event_type='pageview' AND {human} GROUP BY path",(CUTOFF,))
        pages=defaultdict(lambda:{'pageviews':0})
        for row in events:
            p=urlsplit(row['path'] or '/').path
            if p.startswith('/admin'):continue
            pages[p]['pageviews']+=row['pageviews']
        report['top_pages']=[{'path':p,**v} for p,v in sorted(pages.items(),key=lambda item:-item[1]['pageviews'])[:20]]
        report['resource_pageviews']={k:sum(v['pageviews'] for p,v in pages.items() if predicate(p)) for k,predicate in [('guides',lambda p:p.startswith('/guides/')),('reading_challenge',lambda p:p in ['/reading-challenge-2027/','/reto-de-lectura-2027/']),('collections',lambda p:'/collections' in p)]}
        report['country_sessions']=rows(f"SELECT country,count(DISTINCT session_id) sessions FROM live_events WHERE ts>=? AND event_type='pageview' AND {human} GROUP BY country ORDER BY sessions DESC LIMIT 12",(CUTOFF,))
    if 'newsletter_subscribers' in tables:
        report['newsletter']=rows('SELECT active,source,lang,welcome_step,count(*) subscribers FROM newsletter_subscribers GROUP BY active,source,lang,welcome_step')
        report['newsletter_dates']=rows('SELECT min(created_at) first,max(created_at) last,count(*) total FROM newsletter_subscribers')[0]
    if 'pinterest_pins' in tables:
        report['pinterest_records']=rows('SELECT status,kind,count(*) records,min(created_at) first,max(created_at) last FROM pinterest_pins GROUP BY status,kind')
        report['pinterest_recent']=rows('SELECT product_slug,kind,status,created_at FROM pinterest_pins ORDER BY created_at DESC LIMIT 12')
    report['product_counts']=rows('SELECT supplier,active,count(*) products FROM products GROUP BY supplier,active')
    db.close()
    from services import pinterest as pin
    from services import pinterest_jobs as jobs
    report['pinterest_config']={'configured':pin.is_configured(),'token_health':pin.token_health(),'auto_enabled':jobs.auto_pin_enabled(),'launch_enabled':jobs.launch_pin_enabled(),'pins_per_day':jobs.pins_per_day(),'cooldown_days':jobs.repin_cooldown_days()}
    try:
        import asyncio
        profile=asyncio.run(pin.api_request('GET','/user_account'))
        report['pinterest_profile']={k:profile.get(k) for k in ['username','account_type','website_url']}
        boards=asyncio.run(pin.api_request('GET','/boards',params={'page_size':100}))
        report['pinterest_boards']=[{k:b.get(k) for k in ['name','privacy','pin_count']} for b in boards.get('items',[])]
        metrics=asyncio.run(pin.api_request('GET','/user_account/analytics',params={
            'start_date':(NOW-timedelta(days=30)).strftime('%Y-%m-%d'),
            'end_date':(NOW-timedelta(days=1)).strftime('%Y-%m-%d'),
            'metric_types':'IMPRESSION,OUTBOUND_CLICK,SAVE'}))
        report['pinterest_analytics']={k:v.get('summary_metrics') for k,v in metrics.items() if isinstance(v,dict)}
    except Exception as exc:
        report['pinterest_analytics']={'unavailable':type(exc).__name__}
    cron=[]
    markers=['pinterest','daily_social_post.py','send_welcome_series.py','indexnow_submit.py']
    for p in Path('/etc/cron.d').glob('*'):
        if not p.is_file():continue
        for line in p.read_text(errors='replace').splitlines():
            if not line.lstrip().startswith('#') and any(m in line for m in markers):cron.append({'file':p.name,'entry':line})
    for user in ['root','www-data']:
        proc=subprocess.run(['crontab','-l','-u',user],capture_output=True,text=True)
        for line in proc.stdout.splitlines():
            if not line.lstrip().startswith('#') and any(m in line for m in markers):cron.append({'file':'crontab:'+user,'entry':line})
    report['organic_cron_entries']=cron
    for name in ['pin_campaign_done.json','indexnow_state.json']:
        p=ROOT/'data'/name
        if p.exists():
            try:
                d=json.loads(p.read_text());report[name]={'entries':len(d),'mtime_utc':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()}
                if name=='pin_campaign_done.json':report[name]['keys']=list(d)
            except ValueError:report[name]={'error':'invalid JSON'}
        else:report[name]={'exists':False}
    for name in ['tbw-indexnow.log','tbw-welcome.log','tbw-pinterest-auto.log']:
        p=Path('/var/log')/name
        if p.exists():
            text=p.read_text(errors='replace')
            report[name]={'bytes':p.stat().st_size,'mtime_utc':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()}
            if name=='tbw-indexnow.log':report[name]['signals']=[l for l in text.splitlines() if l.startswith(('sitemap ','submitted ','key file '))][-15:]
            if name=='tbw-welcome.log':report[name]['run_signals']=[l for l in text.splitlines() if re.match(r'^\d{4}-\d\d-\d\d \d\d:\d\d \d+ welcome letter',l)][-8:]
    encoded=json.dumps(report,ensure_ascii=False,indent=2).encode()
    with tempfile.TemporaryDirectory(prefix='tbw-organic-audit-') as tmp:
        p=Path(tmp)/'report.json';p.write_bytes(encoded);os.chmod(p,0o600)
        subprocess.run(['openssl','cms','-encrypt','-binary','-aes256','-in',str(p),'-out',sys.argv[2],'-outform','DER',sys.argv[1]],check=True)
    print('Aggregate organic audit finished. No posts, emails or indexing submissions sent.')

if __name__=='__main__':main()
