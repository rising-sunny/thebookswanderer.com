"""Scheduled bounded discovery, extraction and once-per-site invitations."""
import argparse,fcntl,json,sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));load_dotenv(ROOT/'.env')
from services import collaborators_store as store
from services import outreach
from discover_literary_sources import run as discover
from collect_collaborators import run as collect
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--send',action='store_true');args=parser.parse_args()
    store.init_store()
    with (store.data_dir()/'reader-pipeline.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print(json.dumps({'status':'already_running'}));sys.exit(0)
        result={'discovery':discover(),'collection':collect(limit=20),'campaign':outreach.run('store-invitation',[],send=args.send,automatic=True)}
        print(json.dumps(result,ensure_ascii=False));sys.exit(1 if result['campaign'].get('totals',{}).get('uncertain') else 0)
