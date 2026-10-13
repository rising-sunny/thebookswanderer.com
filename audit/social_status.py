"""Read-only production audit. No publishing calls or application writes."""
import hashlib,json,os,pwd,re,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import httpx
from dotenv import load_dotenv

ROOT=Path('/var/www/thebookswanderer.com/server')
load_dotenv(ROOT/'.env')
TOKEN=(os.getenv('FB_PAGE_TOKEN') or '').strip()
PAGE=(os.getenv('FB_PAGE_ID') or '').strip()
BASE=(os.getenv('PUBLIC_BASE_URL') or 'https://thebookswanderer.com').rstrip('/')
STATE=Path(os.getenv('SOCIAL_POST_STATE',ROOT/'data/social_posts.json'))
NOW=datetime.now(timezone.utc)
NY=ZoneInfo('America/New_York')

def clean(s):
    s=str(s)
    if TOKEN:s=s.replace(TOKEN,'[redacted]')
    s=re.sub(r'(?i)(access_token|input_token|password|secret|api_key)(=|\":\s*\")[^\s&\"]+',r'\1\2[redacted]',s)
    return s

def command(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=30)
    return {'returncode':p.returncode,'stdout':clean(p.stdout.strip()),'stderr':clean(p.stderr.strip())}

def file_info(p):
    if not p.exists():return {'exists':False}
    s=p.stat()
    return {'exists':True,'owner':pwd.getpwuid(s.st_uid).pw_name,'mode':oct(s.st_mode&0o777),
            'bytes':s.st_size,'mtime_utc':datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat()}

def graph(client,path,**params):
    try:
        r=client.get('https://graph.facebook.com/v21.0/'+path,params={'access_token':TOKEN,**params})
        d=r.json()
        if 'error' in d:
            err=d['error']
            return {'error':{k:clean(err[k]) if k=='message' else err[k] for k in ['code','error_subcode','type','message'] if k in err},'http_status':r.status_code}
        return d
    except Exception as exc:return {'error':clean(str(exc))}

def main():
    report={'checked_utc':NOW.isoformat(),'checked_new_york':NOW.astimezone(NY).isoformat(),
            'publishing_executed':False,'social_enabled':(os.getenv('SOCIAL_POST_ENABLED','1') or '').strip()!='0',
            'credential_presence':{'page_id':bool(PAGE),'page_token':bool(TOKEN)},
            'server_timezone':command(['timedatectl','show','-p','Timezone','--value']),
            'cron_service':command(['systemctl','is-active','cron']),
            'cron_enabled':command(['systemctl','is-enabled','cron'])}
    target=Path('/etc/cron.d/tbw-social-post')
    report['cron_file']={**file_info(target),'content':clean(target.read_text()) if target.exists() else ''}
    duplicates=[]
    for file in Path('/etc/cron.d').glob('*'):
        if not file.is_file():continue
        for line in file.read_text(errors='replace').splitlines():
            if not line.lstrip().startswith('#') and any(n in line for n in ['daily_social_post.py','post_product_fb.py','fb_post.py']):
                duplicates.append({'source':str(file),'line':clean(line)})
    for user in ['root','www-data']:
        result=command(['crontab','-l','-u',user])
        for line in result['stdout'].splitlines():
            if not line.lstrip().startswith('#') and 'daily_social_post.py' in line:
                duplicates.append({'source':'crontab:'+user,'line':line})
    report['social_cron_entries']=duplicates
    journal=command(['journalctl','-u','cron','--since','8 days ago','--utc','--no-pager','-o','short-iso'])
    report['cron_journal']=[line for line in journal['stdout'].splitlines() if 'daily_social_post.py' in line][-20:]
    report['journal_error']=journal['stderr']
    report['ffmpeg']=command(['ffmpeg','-version'])['stdout'].splitlines()[:1]
    script=ROOT/'scripts/daily_social_post.py'
    report['publisher_sha256']=hashlib.sha256(script.read_bytes()).hexdigest()
    report['fonts_present']=[p.name for p in (ROOT/'social/fonts').glob('*.ttf')]
    report['music_files']=[p.name for p in (ROOT/'social/music').glob('*') if p.is_file()]
    report['state_file']={'path':str(STATE),**file_info(STATE)}
    report['www_data_access']={kind:command(['runuser','-u','www-data','--','test',flag,str(STATE if kind=='read_state' else STATE.parent)])['returncode']==0 for kind,flag in [('read_state','-r'),('write_state_directory','-w')]}
    try:
        entries=json.loads(STATE.read_text());assert isinstance(entries,list)
        report['state_parse']='ok'
    except Exception as exc:
        entries=[];report['state_parse']=clean(str(exc))
    def summary(e):
        return {k:clean(e[k]) if k.endswith('_error') else e[k] for k in ['date','at','slug','ok','facebook','instagram','facebook_error','instagram_error'] if k in e}
    report['state_entries_total']=len(entries)
    report['recent_entries']=[summary(e) for e in entries[-20:]]
    report['state_totals']={'both_success':sum(bool(e.get('ok')) for e in entries),
                            'facebook_success':sum(bool(e.get('facebook')) for e in entries),
                            'instagram_success':sum(bool(e.get('instagram')) for e in entries),
                            'not_both':sum(not bool(e.get('ok')) for e in entries)}
    log=Path('/var/log/tbw-social.log');report['log_file']=file_info(log)
    if log.exists():
        lines=log.read_text(errors='replace').splitlines()[-1500:]
        report['recent_log_signals']=[clean(line) for line in lines if 'pinterest' not in line.lower() and any(t in line for t in ['facebook:','instagram:','rendered ','already posted','SOCIAL_POST_ENABLED','Traceback','PermissionError','FileNotFoundError','RuntimeError','missing'])][-80:]
    next_run=NOW.astimezone(NY).replace(hour=11,minute=3,second=0,microsecond=0)
    if next_run<=NOW.astimezone(NY):next_run+=timedelta(days=1)
    report['next_nominal_run']={'new_york':next_run.isoformat(),'utc':next_run.astimezone(timezone.utc).isoformat()}
    with httpx.Client(timeout=25) as client:
        try:
            products=client.get(BASE+'/api/products').json()['products']
            last={e['slug']:e['date'] for e in entries}
            candidates=sorted(products,key=lambda p:(last.get(p['slug'],''),-p['id']))
            report['active_product_count']=len(products)
            report['next_product_current_rotation']={k:candidates[0][k] for k in ['id','slug','title']} if candidates else None
        except Exception as exc:report['catalog_error']=clean(str(exc))
        if PAGE and TOKEN:
            info=graph(client,PAGE,fields='id,name,instagram_business_account{id,username}')
            report['meta_page']=info
            debug=graph(client,'debug_token',input_token=TOKEN)
            d=debug.get('data',debug)
            report['token_debug']={k:d[k] for k in ['is_valid','type','expires_at','data_access_expires_at','scopes','error'] if k in d}
            report['facebook_recent_posts']=graph(client,PAGE+'/published_posts',fields='id,created_time,permalink_url',limit=5)
            if entries:
                newest=next((e for e in reversed(entries) if e.get('facebook')),None)
                if newest:report['last_facebook_video']=graph(client,str(newest['facebook']),fields='id,created_time,status,permalink_url')
            ig_id=(info.get('instagram_business_account') or {}).get('id')
            if ig_id:report['instagram_recent_media']=graph(client,str(ig_id)+'/media',fields='id,media_type,media_product_type,timestamp,permalink',limit=5)
            # Paging URLs from Graph contain credentials: retain only selected data.
            for k in ['facebook_recent_posts','instagram_recent_media']:
                if k in report and 'data' in report[k]:report[k]={'data':report[k]['data']}
    raw=clean(json.dumps(report,ensure_ascii=False,indent=2)).encode()
    import tempfile
    with tempfile.TemporaryDirectory(prefix='tbw-social-report-') as tmp:
        p=Path(tmp)/'report.json';p.write_bytes(raw);os.chmod(p,0o600)
        subprocess.run(['openssl','cms','-encrypt','-binary','-aes256','-in',str(p),'-out',sys.argv[2],'-outform','DER',sys.argv[1]],check=True)
    print('Read-only social audit finished; encrypted report created. No posts published.')

if __name__=='__main__':main()
