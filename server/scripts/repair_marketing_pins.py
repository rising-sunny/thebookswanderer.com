"""Repair shipping copy on existing pins and publish missing product pins.

Default is a plan only. --apply updates descriptions and backfills never-pinned
active products; existing media, variant titles and destination links are preserved.
"""
import argparse,asyncio,json,re,sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));load_dotenv(ROOT/'.env')
from database import SessionLocal,init_db
from models import PinterestPin,Product
from services import pinterest as pin,pinterest_jobs as jobs

WORLDWIDE=re.compile(r'(?:with\s+)?free\s+(?:worldwide\s+shipping|shipping\s+worldwide)[.!]?',re.I)
def corrected_description(description,product):
    return WORLDWIDE.sub(pin.shipping_copy(product),description)[:800]

async def run(apply=False):
    init_db();db=SessionLocal();result={'apply':apply,'updated':0,'already_current':0,'backfilled':[],'failures':[]}
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
                if apply:await pin.api_request('PATCH','/pins/'+record.pin_id,json={'description':wanted})
                result['updated']+=1
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
        return result
    finally:db.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    result=asyncio.run(run(args.apply));print(json.dumps(result,ensure_ascii=False));sys.exit(1 if result['failures'] else 0)
