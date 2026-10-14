"""Read-only Meta access and website aggregates. No tokens or visitor rows in output."""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv(Path.cwd() / '.env')
now = datetime.now(timezone.utc)
local = ZoneInfo('America/Santiago')
report = {'generated_at': now.astimezone(local).isoformat(), 'meta_access': []}

def get(client, token, path, **params):
    response = client.get('https://graph.facebook.com/v21.0/' + path, headers={'Authorization': 'Bearer ' + token}, params=params)
    body = response.json()
    if 'error' in body:
        error = body['error']
        return {'unavailable': True, 'http_status': response.status_code, 'code': error.get('code'), 'subcode': error.get('error_subcode')}
    return body

with httpx.Client(timeout=20, follow_redirects=False) as client:
    seen=set()
    for name in ('META_CAPI_TOKEN','FB_PAGE_TOKEN'):
        token=os.getenv(name,'').strip()
        if not token or token in seen:continue
        seen.add(token)
        access={'configuration':name}
        try:
            debug=get(client,token,'debug_token',input_token=token)
            if 'data' in debug:
                data=debug['data'];access.update(valid=data.get('is_valid'),scopes=data.get('scopes'),expires_at=data.get('expires_at'))
            accounts=get(client,token,'me/adaccounts',fields='id,name,currency,timezone_name,account_status',limit=30)
            if accounts.get('unavailable'):
                access['accounts']=accounts
            else:
                access['accounts']=[]
                for account in accounts.get('data',[]):
                    row={**account}
                    row['ads']=get(client,token,account['id']+'/ads',fields='id,name,status,effective_status,campaign{id,name,status,objective},adset{id,name,daily_budget,lifetime_budget,status}',limit=50)
                    row['insights_7d']=get(client,token,account['id']+'/insights',date_preset='last_7d',level='ad',fields='ad_id,ad_name,campaign_name,spend,impressions,reach,clicks,inline_link_clicks,ctr,cpc,cpm,actions,action_values',limit=50)
                    row['insights_today']=get(client,token,account['id']+'/insights',date_preset='today',level='ad',fields='ad_id,ad_name,spend,impressions,clicks,inline_link_clicks,actions',limit=50)
                    access['accounts'].append(row)
        except Exception as exc:access['error_type']=type(exc).__name__
        report['meta_access'].append(access)

url=make_url(os.getenv('DATABASE_URL','sqlite:///'+str(Path.cwd()/'data/store.db')))
if url.drivername.startswith('sqlite'):
    con=sqlite3.connect(Path(url.database).resolve().as_uri()+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    start=now-timedelta(days=30)
    rows=con.execute("SELECT ts,session_id,event_type,source,medium,campaign,referrer_domain,ua_class,value_usd FROM live_events WHERE ts>=? ORDER BY ts",(start.replace(tzinfo=None).isoformat(sep=' '),)).fetchall()
    def summary(selected):
        human=[r for r in selected if (r['ua_class'] or '') not in ('server','datacenter')]
        return {'sessions':len({r['session_id'] for r in human}), 'pageviews':sum(r['event_type']=='pageview' for r in human), **{e+'_sessions':len({r['session_id'] for r in human if r['event_type']==e}) for e in ('product_view','add_to_cart','checkout_start','payment_redirect')},'purchases':sum(r['event_type']=='purchase' for r in selected),'revenue_usd':round(sum((r['value_usd'] or 0) for r in selected if r['event_type']=='purchase'),2)}
    def meta(r):
        src=(r['source'] or '').lower();ref=(r['referrer_domain'] or '').lower()
        return src in ('meta','facebook','fb','instagram','ig','threads') or any(host in src or host in ref for host in ('facebook.','instagram.','fb.','threads.'))
    def timestamp(r):return datetime.fromisoformat(r['ts']).replace(tzinfo=timezone.utc)
    report['website']={'window_start':start.astimezone(local).isoformat(),'window_end':now.astimezone(local).isoformat(),'all_30d':summary(rows),'meta_30d':summary([r for r in rows if meta(r)])}
    recent=[r for r in rows if timestamp(r)>=now-timedelta(days=7)]
    report['website']['all_7d']=summary(recent)
    report['website']['meta_7d']=summary([r for r in recent if meta(r)])
    report['website']['meta_daily']=[{'date':(now.astimezone(local).date()-timedelta(days=i)).isoformat(),**summary([r for r in recent if meta(r) and timestamp(r).astimezone(local).date()==now.astimezone(local).date()-timedelta(days=i)])} for i in reversed(range(7))]
    campaigns={r['campaign'] for r in rows if r['campaign']}
    report['website']['campaigns_30d']=[{'campaign':c,'sources':sorted({r['source'] or '' for r in rows if r['campaign']==c}),**summary([r for r in rows if r['campaign']==c])} for c in sorted(campaigns)]
    con.close()
print('META_REPORT_BEGIN')
print(json.dumps(report,ensure_ascii=False,indent=2))
print('META_REPORT_END')
