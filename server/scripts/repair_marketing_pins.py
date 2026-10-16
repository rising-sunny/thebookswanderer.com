"""Repair shipping copy on existing pins and publish missing product pins.

Default is a plan only. --apply updates descriptions and backfills never-pinned
active products; existing media, variant titles and destination links are preserved.
"""
import argparse,asyncio,json,re,sys,os
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));load_dotenv(ROOT/'.env')
from database import SessionLocal,init_db
from models import PinterestPin,Product
from services import pinterest as pin,pinterest_jobs as jobs,collaborators_store as store

WORLDWIDE=re.compile(r'(?:with\s+)?free\s+(?:worldwide\s+shipping|shipping\s+worldwide)[.!]?',re.I)
def corrected_description(description,product):
    def replacement(match):
        return ('. ' if match.group(0).lower().startswith('with') else '') + pin.shipping_copy(product)
    return re.sub(r'\s+\.', '.', WORLDWIDE.sub(replacement, description))[:800]

async def run(apply=False):
    init_db();db=SessionLocal();result={'apply':apply,'updated':0,'already_current':0,'backfilled':[],'failures':[]}
    plan=[]
    try:
        products={p.slug:p for p in db.query(Product).all()}
        records=db.query(PinterestPin).filter(PinterestPin.status=='active',PinterestPin.pin_id!='').order_by(PinterestPin.id).all()
        seen=set()
        for record in records:
            product=products.get(record.product_slug)
            if not product or product.supplier not in ('lulu','printify','digital') or record.pin_id in seen:continue
            seen.add(record.pin_id)
            try:
                live=await pin.api_request('GET','/pins/'+record.pin_id)
                old=live.get('description') or '';wanted=corrected_description(old,product.to_public())
                if old==wanted:result['already_current']+=1;continue
                changed=False
                if apply and not result.get('editing_blocked'):
                    try:
                        await pin.api_request('PATCH','/pins/'+record.pin_id,json={'description':wanted})
                        result['updated']+=1;changed=True
                    except Exception as exc:
                        try:detail=json.loads(getattr(exc,'detail','{}'))
                        except (ValueError,TypeError):detail={}
                        if getattr(exc,'status_code',None)==401 and detail.get('code')==3 and 'pin_edit' in str(detail.get('message','')):
                            result['editing_blocked']={'http_status':401,'provider_code':3,'feature':'pin_edit'}
                        else:raise
                if not changed:
                    plan.append({'pin_id':record.pin_id,'slug':product.slug,'title':live.get('title') or product.title,'description':wanted})
                await asyncio.sleep(.5)
            except Exception as exc:result['failures'].append({'pin_id':record.pin_id,'operation':'description','error_type':type(exc).__name__})
        recorded={row.product_slug for row in records}
        missing=[p for p in products.values() if p.active and p.slug not in recorded]
        for product in missing:
            if not apply:result['backfilled'].append({'slug':product.slug,'planned':True});continue
            try:
                created=await jobs.create_product_pin(db,product,kind='launch')
                if not created.get('ok'):raise RuntimeError('pin not confirmed')
                result['backfilled'].append({'slug':product.slug,'pin_id':created['pin_id']})
            except Exception as exc:result['failures'].append({'slug':product.slug,'operation':'backfill','error_type':type(exc).__name__})
        store.data_dir().mkdir(mode=0o700,parents=True,exist_ok=True)
        target=store.data_dir()/'pinterest_copy_repairs.json'
        temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps({'pending':plan,'editing_blocked':result.get('editing_blocked')},ensure_ascii=False))
        os.chmod(temporary,0o600);temporary.replace(target)
        result['pending_descriptions']=len(plan)
        return result
    finally:db.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    result=asyncio.run(run(args.apply));print(json.dumps(result,ensure_ascii=False));sys.exit(2 if result.get('editing_blocked') else (1 if result['failures'] else 0))
