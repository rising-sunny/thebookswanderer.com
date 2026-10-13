"""Install private PDFs, validate with Lulu, then publish this one physical book.

Default: listing dry run. --apply decrypts the server-bound bundle, validates
both files without creating an order, then upserts only the selected product.
"""
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from services import digital,lulu

SPEC=Path(__file__).with_name('lost_manuscript_product.json')

def apply_product(db,spec,files):
    from models import Product,ProductVariant
    p=db.query(Product).filter(Product.slug==spec['slug']).first()
    if p and p.supplier!='lulu':raise ValueError('Slug belongs to a different supplier')
    if p is None:
        p=Product(slug=spec['slug'],supplier='lulu',cj_pid='lulu',from_country='')
        db.add(p)
    p.title=spec['title'];p.description=spec['description'];p.details_html=spec['details_html']
    p.category=spec['category'];p.price_usd=spec['price_usd'];p.cost_usd=spec['cost_usd']
    p.lulu_package=spec['lulu_package'];p.image_url=spec['image_url']
    p.gallery_json=json.dumps(spec['gallery']);p.active=True
    db.flush()
    v=next((v for v in p.variants if v.name=='English'),None)
    if v is None:v=ProductVariant(product_id=p.id,name='English');db.add(v)
    v.price_usd=spec['price_usd'];v.cost_usd=spec['cost_usd'];v.active=True;v.sort_order=0
    v.cj_vid='lulu-the-lost-manuscript-en';v.cj_sku=''
    v.image_url=spec['image_url'];v.digital_file=files['interior'];v.print_cover=files['cover']
    for other in p.variants:
        if other.name!='English':other.active=False
    return p

def install_files(spec):
    private=digital.digital_dir()/'.release-private'
    key=private/'lost-manuscript.pem'
    bundle=ROOT.parent/'assets/products/the-lost-manuscript/print-bundle.enc'
    if not key.is_file() or not bundle.is_file():raise ValueError('Encrypted bundle or transport key missing')
    with tempfile.TemporaryDirectory(prefix='manuscript-',dir=private) as tmp:
        zipped=Path(tmp)/'bundle.zip'
        subprocess.run(['openssl','cms','-decrypt','-binary','-inform','DER','-inkey',str(key),
                        '-in',str(bundle),'-out',str(zipped)],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        files={}
        with ZipFile(zipped) as z:
            allowed={'manifest.json','lost-manuscript-interior.pdf','lost-manuscript-cover.pdf'}
            if set(z.namelist())!=allowed:raise ValueError('Unexpected bundle members')
            manifest=json.loads(z.read('manifest.json'))
            if manifest['pages']!=spec['pages']:raise ValueError('Page count mismatch')
            for kind in ['interior','cover']:
                member='lost-manuscript-'+kind+'.pdf'
                if z.getinfo(member).file_size>32*1024*1024:raise ValueError('PDF too large')
                data=z.read(member);digest=hashlib.sha256(data).hexdigest()
                if digest!=manifest['sha256'][member] or digest!=spec['sha256'][member]:
                    raise ValueError('Print PDF checksum mismatch')
                if not data.startswith(b'%PDF-'):raise ValueError('Not a PDF')
                name=f'lost-manuscript-en-{kind}-{digest[:12]}.pdf'
                target=digital.digital_dir()/name;pending=target.with_suffix('.tmp')
                pending.write_bytes(data);os.chmod(pending,0o640);pending.replace(target)
                files[kind]=name
    return files

async def validate_files(spec,files):
    base=(os.getenv('PUBLIC_BASE_URL') or 'https://thebookswanderer.com').rstrip('/')
    records={}
    for kind in ['interior','cover']:
        payload={'source_url':lulu.file_url(base,files[kind]),'pod_package_id':spec['lulu_package']}
        if kind=='cover':payload['interior_page_count']=spec['pages']
        result=await lulu.request('POST',f'/validate-{kind}/',payload)
        records[kind]={'id':result['id'],'status':result.get('status')}
    for _ in range(90):
        done=True
        for kind,record in records.items():
            result=await lulu.request('GET',f'/validate-{kind}/{record["id"]}/')
            record['status']=result.get('status')
            if record['status']=='ERROR':
                # Provider messages can include signed URLs: never log them.
                errors=re.sub(r'https?://\S+','[source URL omitted]',str(result.get('errors',[])))
                raise ValueError(f'Lulu {kind} rejected: {errors}')
            if record['status']!='NORMALIZED':done=False
            if kind=='interior' and result.get('page_count') is not None:
                if int(result['page_count'])!=spec['pages']:raise ValueError('Lulu detected wrong page count')
        print('Lulu validation:',json.dumps(records),flush=True)
        if done:return records
        await asyncio.sleep(10)
    raise TimeoutError('Lulu validation still pending; product was not activated')

def main():
    spec=json.loads(SPEC.read_text())
    assert spec['slug']=='the-lost-manuscript' and spec['supplier']=='lulu'
    assert spec['pages']==96 and spec['price_usd']==27.99
    if '--apply' not in sys.argv:
        print(json.dumps({k:spec[k] for k in ['slug','title','supplier','price_usd','pages','lulu_package']},indent=2))
        print('Dry run: no product write, no payment, no print job.')
        return
    if not lulu.configured():raise ValueError('Lulu credentials are not configured on the server')
    files=install_files(spec)
    validation=asyncio.run(validate_files(spec,files))
    from database import init_db,SessionLocal
    init_db()
    with SessionLocal() as db:
        p=apply_product(db,spec,files);db.commit()
        print(f'Published product {p.id}: /products/{p.slug} | English paperback | $27.99')
    report={'slug':spec['slug'],'pages':96,'lulu':validation,'sha256':spec['sha256']}
    (digital.digital_dir()/'.release-private/lost-manuscript-published.json').write_text(json.dumps(report,indent=2))
    print('Both PDFs normalized by Lulu. No print order or payment created.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(re.sub(r'https?://\S+','[URL omitted]',str(exc)),file=sys.stderr)
        sys.exit(1)
