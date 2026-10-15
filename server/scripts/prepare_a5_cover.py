"""Prepare or publish the selected CJ A5 cover. Never creates orders or payments.

--assets checks current supplier data and imports original supplier photographs.
--draft checks the final specification/images, then upserts an inactive listing.
--publish applies the reviewed copy and activates this one selected product.
No arguments prints the intended SKU and retail only.
"""
from __future__ import annotations
import argparse
import asyncio
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from services import cj

PID = '155149A4-8ADA-445F-8F26-44C4596CD754'
VID = '3085EA0A-CC79-4D54-B326-91687DCCA0C7'
SKU = 'CJJJJTJT36003-Navy Blue-A5'
SLUG = 'japanese-a5-book-cover'
PRICE = 19.99
ASSETS = ROOT.parent / 'assets/products' / SLUG
SPEC = Path(__file__).with_name('a5_cover_product.json')


def selected_variant(details):
    if details.get('pid') != PID or details.get('productSku') != 'CJJJJTJT36003':
        raise ValueError('CJ returned a different product')
    variant = next((v for v in details.get('variants', []) if v.get('vid') == VID), None)
    if not variant or variant.get('variantKey') != 'Navy Blue-A5' or variant.get('variantSku') != SKU:
        raise ValueError('The selected A5 cover-only variant has changed')
    cost = float(variant.get('variantSellPrice') or 0)
    if not 0 < cost <= 3.20:
        raise ValueError('The selected variant exceeds the reviewed cost limit')
    return variant


async def validate_supplier():
    details = await cj.get_product_details(pid=PID)
    variant = selected_variant(details)
    await asyncio.sleep(1.3)
    stock = await cj._request('GET', '/product/stock/queryByVid', params={'vid': VID})
    available = sum(int(x.get('totalInventoryNum') or 0) for x in stock if x.get('countryCode') == 'CN')
    if available <= 0:
        raise ValueError('CJ reports no stock for the selected variant')
    quotes = {}
    for zipcode in ('10001', '90001'):
        await asyncio.sleep(1.3)
        options = await cj.freight_calculate(start_country='CN', end_country='US',
                                           products=[{'vid': VID, 'quantity': 1}], zip_code=zipcode)
        if not options:
            raise ValueError('No US shipping route for the selected variant')
        best = min(options, key=lambda x: float(x.get('totalPostageFee', x.get('logisticPrice', 1e9))))
        freight = float(best.get('totalPostageFee', best.get('logisticPrice', 1e9)))
        if not 0 <= freight <= 6.50:
            raise ValueError('US shipping exceeds the reviewed cost limit')
        quotes[zipcode] = {k: best.get(k) for k in ('logisticName', 'logisticAging', 'logisticPrice', 'totalPostageFee')}
    report = {'pid': PID, 'vid': VID, 'sku': SKU, 'cost_usd': float(variant['variantSellPrice']),
              'stock': [{k: x.get(k) for k in ('countryCode', 'cjInventoryNum', 'factoryInventoryNum', 'totalInventoryNum')} for x in stock],
              'quotes': quotes, 'physical_sample_requested': False, 'sales_active': False}
    return details, variant, report


async def import_assets(details, variant):
    # Import only this product's supplier images; no image synthesis or editing.
    urls = [variant.get('variantImage')]
    urls += re.findall(r'src="(https://[^"]+)"', details.get('description') or '')
    urls = list(dict.fromkeys(u for u in urls if u))
    ASSETS.mkdir(parents=True, exist_ok=True)
    downloaded = []
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        for i, source in enumerate(urls[:8]):
            parsed = urlparse(source)
            if parsed.scheme != 'https' or parsed.hostname not in ('cf.cjdropshipping.com', 'oss-cf.cjdropshipping.com'):
                raise ValueError('Unexpected supplier image host')
            response = await client.get(source)
            if response.status_code in (404, 410):
                print('Supplier photograph unavailable:', i, response.status_code, flush=True)
                continue
            response.raise_for_status()
            raw = response.content
            if len(raw) > 12 * 1024 * 1024:
                raise ValueError('Supplier image too large')
            with Image.open(io.BytesIO(raw)) as check:
                if min(check.size) < 400 or check.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('Unexpected supplier photograph format or dimensions')
                extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}[check.format]
                check.verify()
            filename = f'supplier-{i:02d}.{extension}'
            target = ASSETS / filename
            pending = target.with_suffix('.tmp')
            pending.write_bytes(raw)
            pending.replace(target)
            downloaded.append({'filename': filename, 'source': source, 'selected_variant': i == 0})
            print('Imported original supplier photograph:', filename, flush=True)
    if not downloaded:
        raise ValueError('No supplier photographs are available')
    return downloaded


def stage_product(db, spec, cost, *, publish=False):
    from models import Product, ProductVariant
    if (spec['slug'], spec['pid'], spec['vid'], spec['sku'], spec['price_usd']) != (SLUG, PID, VID, SKU, PRICE):
        raise ValueError('Draft specification does not match the reviewed variant')
    product = db.query(Product).filter(Product.slug == SLUG).first()
    if product and (product.supplier != 'cj' or product.cj_pid != PID):
        raise ValueError('The product slug belongs to another supplier product')
    duplicate = db.query(Product).filter(Product.cj_pid == PID, Product.slug != SLUG).first()
    if duplicate:
        raise ValueError('This supplier product already has a different store listing')
    if product and product.active and not publish:
        raise ValueError('An active listing exists; draft preparation must not hide it')
    if product is None:
        product = Product(slug=SLUG, supplier='cj', cj_pid=PID, active=False)
        db.add(product)
    for key in ('title', 'description', 'details_html', 'category', 'price_usd', 'image_url'):
        setattr(product, key, spec[key])
    product.cj_vid = VID; product.cj_sku = SKU; product.cost_usd = cost
    product.from_country = 'CN'; product.active = publish
    product.gallery_json = json.dumps(spec['gallery'])
    db.flush()
    variant = next((v for v in product.variants if v.cj_vid == VID), None)
    if variant is None:
        variant = ProductVariant(product_id=product.id, cj_vid=VID)
        db.add(variant)
    variant.name = spec['variant_name']; variant.cj_sku = SKU
    variant.cost_usd = cost; variant.price_usd = PRICE; variant.image_url = spec['image_url']
    variant.active = True; variant.sort_order = 0
    for other in product.variants:
        if other is not variant:
            other.active = False
    return product


async def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--assets', action='store_true')
    mode.add_argument('--draft', action='store_true')
    mode.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if not args.assets and not args.draft and not args.publish:
        print(json.dumps({'slug': SLUG, 'sku': SKU, 'price_usd': PRICE, 'active': False}))
        return
    details, variant, report = await validate_supplier()
    if args.assets:
        report['images'] = await import_assets(details, variant)
    else:
        spec = json.loads(SPEC.read_text())
        for image in [spec['image_url'], *spec['gallery']]:
            if not (ROOT.parent / image.lstrip('/')).is_file():
                raise ValueError('A reviewed listing image is missing')
        from database import SessionLocal, init_db
        init_db()
        with SessionLocal() as db:
            product = stage_product(db, spec, report['cost_usd'], publish=args.publish)
            db.commit()
            report['product_id'] = product.id
            report['sales_active'] = product.active
        print('Published:' if args.publish else 'Prepared inactive draft:', product.id, SLUG, 'USD', PRICE, flush=True)
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    (data / 'a5-cover-validation.json').write_text(json.dumps(report, indent=2))
    print('Verified supplier variant and US shipping. No customer order, sample order or payment created.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        print(re.sub(r'https?://\S+', '[URL omitted]', str(exc)), file=sys.stderr)
        sys.exit(1)
