"""Read-only preflight by default. --publish upserts the single reviewed print.

Does not create PayPal orders or supplier orders; does not post launch pins.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from services import prodigi_store as prodigi


def stage(db, data, *, publish=False):
    from models import Product, ProductVariant
    if data['slug'] != prodigi.spec()['slug'] or data['supplier_sku']!='GLOBAL-FAP-12X16':
        raise ValueError('Unreviewed product mapping')
    product=db.query(Product).filter_by(slug=data['slug']).first()
    if product and product.supplier!='prodigi':
        raise ValueError('Existing slug belongs to another supplier')
    if product and product.active and not publish:
        raise ValueError('Cannot hide an active product')
    if product is None:
        product=Product(slug=data['slug'],supplier='prodigi');db.add(product)
    for field in ['title','description','details_html','category','image_url','price_usd','cost_usd','from_country']:
        setattr(product,field,data[field])
    product.gallery_json=json.dumps(data['gallery'])
    product.active=publish
    db.flush()
    variants=list(product.variants)
    if len(variants)>1:
        raise ValueError('Unexpected extra variants')
    variant=variants[0] if variants else ProductVariant(product_id=product.id)
    if not variants:db.add(variant)
    variant.name=data['variant_name'];variant.image_url=data['image_url']
    variant.price_usd=data['price_usd'];variant.cost_usd=data['cost_usd'];variant.active=True
    # No CJ identifiers: Prodigi routing comes from the reviewed slug manifest.
    product.cj_pid='';product.cj_vid='';product.cj_sku='';variant.cj_vid='';variant.cj_sku=''
    db.flush()
    return product


async def preflight():
    if not prodigi.ready():
        raise prodigi.ProdigiError('Prodigi runtime flag, credential, signing key or artwork unavailable')
    path=prodigi.asset_path()
    from PIL import Image
    with Image.open(path) as image:
        if image.size!=(3600,4800) or image.mode!='RGB' or not image.info.get('icc_profile'):
            raise prodigi.ProdigiError('Print asset verification failed')
        image.verify()
    await prodigi.product_check()
    from types import SimpleNamespace
    data=prodigi.spec()
    product=SimpleNamespace(supplier='prodigi',slug=data['slug'],id=0,price_usd=data['price_usd'])
    await prodigi.shipping([(product,None,1)],'US')
    return data


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    data=await preflight()
    if not args.publish:
        print(json.dumps({'preflight':'passed','sku':data['supplier_sku'],'supplier_order_created':False}))
        return
    # Ensure the running app can serve the exact print bytes before exposing a purchasable listing.
    import hashlib
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
            asset=await client.get(prodigi.asset_url('https://thebookswanderer.com'))
    except httpx.HTTPError:
        raise prodigi.ProdigiError('Running service artwork check unavailable') from None
    if asset.status_code!=200 or hashlib.sha256(asset.content).hexdigest()!=data['artwork_sha256']:
        raise prodigi.ProdigiError('Running service could not serve the reviewed print asset')
    from database import SessionLocal,init_db
    init_db()
    with SessionLocal() as db:
        try:
            product=stage(db,data,publish=True);db.commit()
            print(json.dumps({'published':True,'product_id':product.id,'slug':product.slug,
                              'price_usd':product.price_usd,'supplier_order_created':False}))
        except Exception:
            db.rollback();raise

if __name__=='__main__':
    try:asyncio.run(main())
    except (prodigi.ProdigiError,ValueError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
