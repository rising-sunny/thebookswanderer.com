"""Restore an uncertain Prodigi mapping by verified supplier ID. GET only."""
import argparse,asyncio,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from database import SessionLocal
from models import Order
from services import prodigi_submission

async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--order-id',type=int,required=True)
    parser.add_argument('--supplier-order-id',required=True)
    args=parser.parse_args()
    with SessionLocal() as db:
        order=db.get(Order,args.order_id)
        if not order:raise ValueError('Order not found')
        reference=await prodigi_submission.reconcile(db,order,args.supplier_order_id)
        print('Restored mapping:',order.id,reference)
if __name__=='__main__':asyncio.run(main())
