"""Prepare manufacturer mockups or publish the reviewed Printify stationery.

--prepare downloads the four manufacturer mockups for each product but never
activates listings. --apply revalidates fulfillment, artwork, price and costs,
then atomically upserts only the two reviewed products. No orders are created.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from services import printify

SPEC = Path(__file__).with_name('reading_stationery_products.json')
EXPECTED = {
    'reading-society-pouch': (1179, 28, 91328, 22.99),
    'letters-from-the-library': (1101, 228, 82165, 29.99),
}


def read_spec():
    release = json.loads(SPEC.read_text())
    if release.get('release') != 'reading-stationery-v1':
        raise ValueError('Unexpected release')
    products = release['products']
    if len(products) != 2 or {p['slug'] for p in products} != set(EXPECTED):
        raise ValueError('Unexpected release products')
    for p in products:
        actual = tuple(p[k] for k in ('blueprint_id', 'provider_id', 'variant_id', 'price_usd'))
        if actual != EXPECTED[p['slug']] or p['supplier'] != 'printify':
            raise ValueError('Unexpected supplier, variant or retail price')
    return products


def verify_supplier(spec, product):
    if (product['id'], product['blueprint_id'], product['print_provider_id']) != (
        spec['printify_id'], spec['blueprint_id'], spec['provider_id']
    ):
        raise ValueError('Supplier product, blueprint or provider mismatch')
    variants = [v for v in product['variants'] if v.get('is_enabled')]
    if len(variants) != 1 or variants[0]['id'] != spec['variant_id'] or not variants[0].get('is_available'):
        raise ValueError('Unexpected or unavailable supplier variant')
    if variants[0]['price'] != round(spec['price_usd'] * 100):
        raise ValueError('Supplier retail differs from the release price')
    areas = [a for a in product['print_areas'] if spec['variant_id'] in a['variant_ids']]
    if len(areas) != 1:
        raise ValueError('Ambiguous print area')
    holders = areas[0]['placeholders']
    if len(holders) != len(spec['uploads']) or {p['position'] for p in holders} != set(spec['uploads']):
        raise ValueError('Unexpected printed sides')
    for holder in holders:
        images = holder.get('images', [])
        expected = spec['uploads'][holder['position']]
        if len(images) != 1 or images[0]['id'] != expected['id']:
            raise ValueError('Artwork upload mismatch')
        image = images[0]
        if (image.get('width'), image.get('height')) != (expected['width'], expected['height']):
            raise ValueError('Artwork dimensions changed')
        if any(abs(float(image.get(k, -99)) - v) > 0.00001 for k, v in
               {'x': .5, 'y': .5, 'scale': 1., 'angle': 0.}.items()) or image.get('flipX') or image.get('flipY'):
            raise ValueError('Reviewed artwork placement changed')
    return variants[0]['cost'] / 100


async def fetch_supplier(spec):
    p = await printify._request('GET', f'/shops/{printify.shop_id()}/products/{spec["printify_id"]}.json')
    cost = verify_supplier(spec, p)
    shipping = await printify.shipping_cost([
        {'product_id': p['id'], 'variant_id': spec['variant_id'], 'quantity': 1}
    ], 'US')
    if cost <= 0 or shipping <= 0 or cost + shipping > spec['max_landed_usd']:
        raise ValueError('Production and shipping exceed the release cost limit')
    return p, {'cost_usd': cost, 'shipping_usd': shipping}


async def prepare_mockups(spec, product):
    cameras = spec['mockup_cameras']
    found = set()
    folder = ROOT.parent / 'assets/products' / spec['slug']
    folder.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
        for mockup in product.get('images', []):
            parsed = urlparse(mockup['src'])
            camera = (parse_qs(parsed.query).get('camera_label') or [''])[0]
            if camera not in cameras or camera in found:
                continue
            if parsed.scheme != 'https' or parsed.hostname not in ('images-api.printify.com', 'images.printify.com'):
                raise ValueError('Unexpected manufacturer mockup host')
            response = await client.get(mockup['src'])
            response.raise_for_status()
            data = response.content
            if not data.startswith(b'\xff\xd8') or len(data) > 12 * 1024 * 1024:
                raise ValueError('Unexpected mockup format or size')
            with Image.open(io.BytesIO(data)) as image:
                if min(image.size) < 600:
                    raise ValueError('Manufacturer mockup resolution too low')
                image.verify()
            target = folder / cameras[camera]
            pending = target.with_suffix('.tmp')
            pending.write_bytes(data)
            pending.replace(target)
            found.add(camera)
    if found != set(cameras):
        raise ValueError('Manufacturer mockups are not ready')


def apply_product(db, spec, info):
    from models import Product, ProductVariant
    conflict = db.query(Product).filter(
        Product.printify_product_id == spec['printify_id'], Product.slug != spec['slug']
    ).first()
    if conflict:
        raise ValueError('Supplier product already belongs to another listing')
    product = db.query(Product).filter(Product.slug == spec['slug']).first()
    if product and (product.supplier != 'printify' or product.printify_product_id not in ('', spec['printify_id'])):
        raise ValueError('Existing slug belongs to a different supplier product')
    if product is None:
        product = Product(slug=spec['slug'])
        db.add(product)
    for key in ('title', 'description', 'details_html', 'category', 'price_usd', 'image_url', 'supplier'):
        setattr(product, key, spec[key])
    product.gallery_json = json.dumps(spec['gallery'])
    product.active = True
    product.cost_usd = info['cost_usd']
    product.from_country = 'US'
    product.printify_product_id = spec['printify_id']
    product.cj_pid = ''; product.cj_vid = ''; product.cj_sku = ''; product.lulu_package = ''
    db.flush()
    variant = next((v for v in product.variants if v.printify_variant_id == spec['variant_id']), None)
    if variant is None:
        variant = ProductVariant(product_id=product.id)
        db.add(variant)
    variant.name = spec['variant_name']
    variant.printify_variant_id = spec['variant_id']
    variant.price_usd = spec['price_usd']; variant.cost_usd = info['cost_usd']
    variant.image_url = spec['image_url']; variant.active = True; variant.sort_order = 0
    variant.cj_vid = ''; variant.cj_sku = ''; variant.digital_file = ''; variant.print_cover = ''
    for other in product.variants:
        if other is not variant:
            other.active = False
    return product


async def execute(mode):
    specs = read_spec()
    verified = []
    for spec in specs:
        supplier_product, info = await fetch_supplier(spec)
        if mode == 'prepare':
            await prepare_mockups(spec, supplier_product)
        if mode == 'apply':
            for path in [spec['image_url'], *spec['gallery']]:
                if not (ROOT.parent / path.lstrip('/')).is_file():
                    raise ValueError('A listing image is missing; run --prepare first')
        verified.append((spec, info))
        print(spec['slug'], json.dumps(info), 'retail', spec['price_usd'], flush=True)
    if mode != 'apply':
        print('Manufacturer artwork, variants and costs verified. No listings activated or orders created.')
        return
    from database import SessionLocal, init_db
    init_db()
    with SessionLocal() as db:
        try:
            products = [apply_product(db, spec, info) for spec, info in verified]
            db.commit()
            print('Published:', json.dumps([{'id': p.id, 'slug': p.slug, 'price_usd': p.price_usd} for p in products]))
        except Exception:
            db.rollback()
            raise
    print('Both listings use existing Printify checkout fulfillment. No orders or production charges created.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    asyncio.run(execute('prepare' if args.prepare else 'apply' if args.apply else 'dry-run'))


if __name__ == '__main__':
    main()
