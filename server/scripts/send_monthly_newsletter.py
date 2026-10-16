"""Monthly opted-in newsletter. Default is dry-run; --send enables scheduled delivery."""
import argparse,json,sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));load_dotenv(ROOT/'.env')
from database import init_db
from services.monthly_newsletter import run
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--send',action='store_true');args=parser.parse_args()
    init_db()
    result=run(send=args.send);print(json.dumps(result))
    sys.exit(1 if result.get('counts',{}).get('uncertain') else 0)
