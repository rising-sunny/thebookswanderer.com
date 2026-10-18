"""Validate or publish the reviewed wooden bedside book rest.

Default: read-only supplier/cost/media validation. --publish activates exactly
one SKU at the approved retail price. Never creates supplier orders or payments.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from services import cj

PID = '2605290228151629500'
VID = '2605290228161620200'
SKU = 'CJYD291394201AZ'
SLUG = 'bedside-book-rest'
PRICE = 24.99
SPEC = Path(__file__).with_name('bedside_book_rest_product.json')
ASSETS = ROOT.parent / 'assets/products' / SLUG
# Checkout upgrades to faster carriers; allow up to $16 landed at the approved
# $24.99 retail (~29% contribution after estimated fees and $0.35 operations).
MAX_LANDED_USD = 16.0


def selected_variant(details):
    if details.get('pid') != PID or details.get('productSku') != 'CJYD2913942':
        raise ValueError('Supplier product identity changed')
    variant = next((v for v in details.get('variants', []) if v.get('vid') == VID), None)
    if not variant or variant.get('variantSku') != SKU or variant.get('variantKey') != 'Wood Color':
        raise ValueError('Selected natural-wood variant changed')
    cost = float(variant.get('variantSellPrice') or 0)
    if not math.isfinite(cost) or not 0 < cost <= 2.50:
        raise ValueError('Supplier unit cost exceeds reviewed limit')
    return variant


def read_spec():
    spec = json.loads(SPEC.read_text())
    if (spec.get('slug'), spec.get('pid'), spec.get('vid'), spec.get('sku'), spec.get('price_usd')) != (SLUG, PID, VID, SKU, PRICE):
        raise ValueError('Specification identity or approved retail changed')
    if spec.get('physical_sample_requested') is not False:
        raise ValueError('Unexpected sample configuration')
    for path in [spec['image_url'], *spec['gallery']]:
        if not path.startswith(f'/assets/products/{SLUG}/') or '..' in Path(path).parts:
            raise ValueError('Listing media must belong to this product')
        if not (ROOT.parent / path.lstrip('/')).is_file():
            raise ValueError('A reviewed photograph is missing')
    provenance = json.loads((ASSETS / 'sources.json').read_text())
    if (provenance.get('pid'), provenance.get('vid')) != (PID, VID):
        raise ValueError('Photographs belong to a different supplier variant')
    hashes = {row['file']: row['sha256'] for row in provenance['images']}
    for path in [spec['image_url'], *spec['gallery']]:
        file = ROOT.parent / path.lstrip('/')
        if hashes.get(file.name) != hashlib.sha256(file.read_bytes()).hexdigest():
            raise ValueError('Reviewed supplier photograph changed')
    return spec


async def validate_supplier():
    from main import _pick_freight  # match the carrier actually chosen at checkout
    details = await cj.get_product_details(pid=PID)
    variant = selected_variant(details)
    await asyncio.sleep(1.3)
    stock = await cj._request('GET', '/product/stock/queryByVid', params={'vid': VID})
    available = sum(int(s.get('totalInventoryNum') or 0) for s in stock if s.get('countryCode') == 'CN')
    if available <= 0:
        raise ValueError('Selected variant has no available China stock')
    quotes = {}
    for zipcode in (None, '10001', '90001'):
        await asyncio.sleep(1.3)
        options = await cj.freight_calculate(start_country='CN', end_country='US',
                    products=[{'vid': VID, 'quantity': 1}], zip_code=zipcode)
        if not options:
            raise ValueError('No US shipping route for this variant')
        chosen = _pick_freight(options)
        freight = float(chosen.get('totalPostageFee') or chosen.get('logisticPrice') or 0)
        landed = float(variant['variantSellPrice']) + freight
        if not math.isfinite(freight) or freight <= 0 or landed > MAX_LANDED_USD:
            raise ValueError('Checkout carrier exceeds reviewed landed-cost limit')
        quotes[zipcode or 'US-default'] = {
            'carrier': chosen.get('logisticName'), 'transit_days': chosen.get('logisticAging'),
            'shipping_usd': freight, 'landed_usd': round(landed, 2),
        }
    return {'pid': PID, 'vid': VID, 'sku': SKU, 'cost_usd': float(variant['variantSellPrice']),
            'china_stock_declared': available, 'quotes': quotes,
            'physical_sample_requested': False, 'orders_created': 0, 'payments_made': 0}


def stage_product(db, spec, cost, *, publish=False):
    from models import Product, ProductVariant
    if (spec.get('slug'), spec.get('pid'), spec.get('vid'), spec.get('sku'), spec.get('price_usd')) != (SLUG, PID, VID, SKU, PRICE):
        raise ValueError('Specification identity or approved retail changed')
    if not math.isfinite(cost) or not 0 < cost <= 2.50:
        raise ValueError('Supplier cost exceeds reviewed limit')
    product = db.query(Product).filter(Product.slug == SLUG).first()
    if product and (product.supplier != 'cj' or product.cj_pid != PID):
        raise ValueError('Slug belongs to another supplier product')
    if db.query(Product).filter(Product.cj_pid == PID, Product.slug != SLUG).first():
        raise ValueError('Supplier product already has a different store listing')
    if product and product.active and not publish:
        raise ValueError('An active listing cannot be hidden by preparing a draft')
    if product is None:
        product = Product(slug=SLUG, supplier='cj', cj_pid=PID, active=False)
        db.add(product)
    for key in ('title', 'description', 'details_html', 'category', 'image_url'):
        setattr(product, key, spec[key])
    product.price_usd = PRICE; product.cost_usd = cost
    product.cj_vid = VID; product.cj_sku = SKU; product.from_country = 'CN'
    product.active = publish; product.gallery_json = json.dumps(spec['gallery'])
    db.flush()
    variant = next((v for v in product.variants if v.cj_vid == VID), None)
    if variant is None:
        variant = ProductVariant(product_id=product.id, cj_vid=VID)
        db.add(variant)
    variant.name = spec['variant_name']; variant.cj_sku = SKU
    variant.price_usd = PRICE; variant.cost_usd = cost
    variant.image_url = spec['image_url']; variant.active = True; variant.sort_order = 0
    for other in product.variants:
        if other is not variant:
            other.active = False
    db.flush()
    return product


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    spec = read_spec()
    report = await validate_supplier()
    report['price_usd'] = PRICE
    report['sales_active'] = False
    if args.publish:
        from database import SessionLocal
        # The normal deployed application owns schema initialization. This script
        # only changes the reviewed product and its variant, within one transaction.
        with SessionLocal() as db:
            product = stage_product(db, spec, report['cost_usd'], publish=True)
            db.commit()
            report['product_id'] = product.id
            report['variant_id'] = product.default_variant().id
            report['sales_active'] = product.active
        (ROOT / 'data/bedside-book-rest-validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f'Book rest publication stopped: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
