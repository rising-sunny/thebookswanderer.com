"""Validate and publish the two original Reading Society products.

--validate installs the encrypted print files, downloads the manufacturer's
mockups, and validates both PDFs with Lulu. --apply requires that validation
and upserts only these two products. Neither mode creates a customer order.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from services import digital, lulu, printify

SPEC = Path(__file__).with_name('reader_collection_products.json')
BOOK = 'book-club-companion'
TOTE = 'reading-society-tote'


def read_spec():
    spec = json.loads(SPEC.read_text())
    if {p['slug'] for p in spec['products']} != {BOOK, TOTE}:
        raise ValueError('Unexpected release products')
    book = next(p for p in spec['products'] if p['slug'] == BOOK)
    tote = next(p for p in spec['products'] if p['slug'] == TOTE)
    if book['pages'] != 100 or book['price_usd'] != 24.99 or tote['price_usd'] != 27.99:
        raise ValueError('Unexpected edition or retail price')
    return spec, book, tote


def private_folder():
    folder = digital.digital_dir() / '.release-private'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder


def install_files(book):
    # Reuse the existing server-bound encryption transport. Its private key
    # never leaves the server; the repository contains only CMS ciphertext.
    key = private_folder() / 'lost-manuscript.pem'
    bundle = ROOT.parent / 'assets/products/book-club-companion/print-bundle.enc'
    if not key.is_file() or not bundle.is_file():
        raise ValueError('Server transport key or encrypted print bundle is missing')
    files = {}
    with tempfile.TemporaryDirectory(prefix='book-club-', dir=private_folder()) as tmp:
        zipped = Path(tmp) / 'bundle.zip'
        subprocess.run(['openssl', 'cms', '-decrypt', '-binary', '-inform', 'DER',
                        '-inkey', str(key), '-in', str(bundle), '-out', str(zipped)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with ZipFile(zipped) as z:
            allowed = {'manifest.json', 'book-club-companion-interior.pdf', 'book-club-companion-cover.pdf'}
            if set(z.namelist()) != allowed:
                raise ValueError('Unexpected encrypted bundle members')
            manifest = json.loads(z.read('manifest.json'))
            if manifest['pages'] != book['pages']:
                raise ValueError('Page count mismatch')
            for kind in ('interior', 'cover'):
                member = f'book-club-companion-{kind}.pdf'
                if z.getinfo(member).file_size > 32 * 1024 * 1024:
                    raise ValueError('Print file too large')
                data = z.read(member)
                digest = hashlib.sha256(data).hexdigest()
                if not data.startswith(b'%PDF-') or digest != manifest['sha256'][member] or digest != book['sha256'][member]:
                    raise ValueError('Print file checksum mismatch')
                name = f'book-club-companion-en-{kind}-{digest[:12]}.pdf'
                target = digital.digital_dir() / name
                pending = target.with_suffix('.tmp')
                pending.write_bytes(data)
                os.chmod(pending, 0o640)
                pending.replace(target)
                files[kind] = name
    return files


async def tote_info(tote, download=False):
    product = await printify._request('GET', f'/shops/{printify.shop_id()}/products/{tote["printify_id"]}.json')
    variants = [v for v in product.get('variants', []) if v.get('is_enabled')]
    if product.get('blueprint_id') != 1313 or product.get('print_provider_id') != 99:
        raise ValueError('Tote blueprint or provider mismatch')
    if len(variants) != 1 or variants[0]['id'] != 101409 or not variants[0].get('is_available'):
        raise ValueError('Natural tote variant is unavailable or incorrectly configured')
    area = next((a for a in product.get('print_areas', []) if 101409 in a.get('variant_ids', [])), {})
    front = next((p for p in area.get('placeholders', []) if p.get('position') == 'front'), {})
    if len(front.get('images', [])) != 1 or front['images'][0]['id'] != tote['artwork_upload_id']:
        raise ValueError('Original artwork mapping mismatch')
    cost = variants[0]['cost'] / 100
    ship = await printify.shipping_cost([{'product_id': product['id'], 'variant_id': 101409, 'quantity': 1}], 'US')
    if cost + ship > 16.50:
        raise ValueError('Tote production and shipping exceed the release cost limit')
    if download:
        wanted = {'front': 'main_en.jpg', 'person-front': 'worn_en.jpg',
                  'context-front': 'detail_en.jpg', 'lifestyle-front': 'lifestyle_en.jpg'}
        folder = ROOT.parent / 'assets/products/reading-society-tote'
        folder.mkdir(parents=True, exist_ok=True)
        found = set()
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            for image in product.get('images', []):
                source = image.get('src', '')
                parsed = urlparse(source)
                label = (parse_qs(parsed.query).get('camera_label') or [''])[0]
                if label not in wanted or label in found:
                    continue
                if parsed.scheme != 'https' or parsed.hostname not in ('images-api.printify.com', 'images.printify.com'):
                    raise ValueError('Unexpected mockup host')
                response = await client.get(source)
                response.raise_for_status()
                if not response.content.startswith(b'\xff\xd8') or len(response.content) > 12 * 1024 * 1024:
                    raise ValueError('Unexpected manufacturer mockup file')
                target = folder / wanted[label]
                pending = target.with_suffix('.tmp')
                pending.write_bytes(response.content)
                with Image.open(pending) as check:
                    if min(check.size) < 600:
                        raise ValueError('Manufacturer mockup resolution too small')
                    check.verify()
                pending.replace(target)
                found.add(label)
        if found != set(wanted):
            raise ValueError('Manufacturer mockups are not ready')
    return {'product_id': product['id'], 'variant_id': 101409, 'cost_usd': cost, 'shipping_usd': ship}


async def validate_book(book, files):
    base = (os.getenv('PUBLIC_BASE_URL') or 'https://thebookswanderer.com').rstrip('/')
    records = {}
    for kind in ('interior', 'cover'):
        payload = {'source_url': lulu.file_url(base, files[kind]), 'pod_package_id': book['lulu_package']}
        if kind == 'cover':
            payload['interior_page_count'] = book['pages']
        result = await lulu.request('POST', f'/validate-{kind}/', payload)
        records[kind] = {'id': result['id'], 'status': result.get('status')}
    for _ in range(90):
        done = True
        for kind, record in records.items():
            result = await lulu.request('GET', f'/validate-{kind}/{record["id"]}/')
            record['status'] = result.get('status')
            if record['status'] == 'ERROR':
                errors = re.sub(r'https?://\S+', '[source URL omitted]', str(result.get('errors', [])))
                raise ValueError(f'Lulu {kind} rejected: {errors}')
            if record['status'] != 'NORMALIZED':
                done = False
            if kind == 'interior' and result.get('page_count') is not None and int(result['page_count']) != book['pages']:
                raise ValueError('Lulu detected a different page count')
        print('Lulu validation:', json.dumps(records), flush=True)
        if done:
            return records
        await asyncio.sleep(10)
    raise TimeoutError('Lulu validation pending; product remains unpublished')


def apply_product(db, spec, *, files=None, tote=None):
    from models import Product, ProductVariant
    product = db.query(Product).filter(Product.slug == spec['slug']).first()
    if product and product.supplier != spec['supplier']:
        raise ValueError('Product slug belongs to a different supplier')
    if product is None:
        product = Product(slug=spec['slug'])
        db.add(product)
    for key in ('title', 'description', 'details_html', 'category', 'price_usd', 'image_url', 'supplier'):
        setattr(product, key, spec[key])
    product.gallery_json = json.dumps(spec['gallery'])
    product.active = True
    product.cj_pid = 'lulu' if spec['supplier'] == 'lulu' else ''
    product.cj_vid = ''; product.cj_sku = ''
    product.cost_usd = spec['cost_usd'] if files else tote['cost_usd']
    product.from_country = '' if files else 'US'
    product.lulu_package = spec.get('lulu_package', '')
    product.printify_product_id = spec.get('printify_id', '')
    db.flush()
    name = 'English paperback' if files else 'Natural canvas · green print'
    variant = next((v for v in product.variants if v.name == name), None)
    if variant is None:
        variant = ProductVariant(product_id=product.id, name=name)
        db.add(variant)
    variant.price_usd = spec['price_usd']; variant.cost_usd = product.cost_usd
    variant.image_url = spec['image_url']; variant.active = True; variant.sort_order = 0
    variant.cj_vid = 'lulu-book-club-companion-en' if files else ''
    variant.cj_sku = ''
    variant.printify_variant_id = 0 if files else tote['variant_id']
    variant.digital_file = files['interior'] if files else ''
    variant.print_cover = files['cover'] if files else ''
    for other in product.variants:
        if other is not variant:
            other.active = False
    return product


async def execute(mode):
    spec, book, tote = read_spec()
    if mode == 'dry-run':
        print(json.dumps([{k: p[k] for k in ('slug', 'title', 'supplier', 'price_usd')} for p in spec['products']], indent=2))
        return
    if not lulu.configured() or not printify.configured():
        raise ValueError('Existing supplier credentials are not configured')
    report_path = private_folder() / 'reader-collection-validated.json'
    if mode == 'validate':
        files = install_files(book)
        info = await tote_info(tote, download=True)
        validation = await validate_book(book, files)
        report = {'release': spec['release'], 'sha256': book['sha256'], 'files': files,
                  'lulu': validation, 'tote': info}
        report_path.write_text(json.dumps(report, indent=2))
        print('Both Lulu PDFs normalized and Printify artwork, variant, cost and mockups verified. No listings activated.')
        return
    if not report_path.is_file():
        raise ValueError('Run --validate successfully before publishing')
    report = json.loads(report_path.read_text())
    if report['release'] != spec['release'] or report['sha256'] != book['sha256']:
        raise ValueError('Validated release does not match current files')
    for kind in ('interior', 'cover'):
        path = digital.file_path(report['files'][kind])
        if not path or hashlib.sha256(path.read_bytes()).hexdigest() != book['sha256'][f'book-club-companion-{kind}.pdf']:
            raise ValueError('Validated print file is missing or changed')
        current = await lulu.request('GET', f'/validate-{kind}/{report["lulu"][kind]["id"]}/')
        if current.get('status') != 'NORMALIZED':
            raise ValueError('Lulu validation no longer confirms print readiness')
    info = await tote_info(tote)
    for p in spec['products']:
        for image in [p['image_url'], *p['gallery']]:
            if not (ROOT.parent / image.lstrip('/')).is_file():
                raise ValueError('A listing image is missing')
    from database import SessionLocal, init_db
    init_db()
    with SessionLocal() as db:
        book_product = apply_product(db, book, files=report['files'])
        tote_product = apply_product(db, tote, tote=info)
        db.commit()
        published = [{'id': p.id, 'slug': p.slug, 'price_usd': p.price_usd} for p in (book_product, tote_product)]
    (private_folder() / 'reader-collection-published.json').write_text(json.dumps({'release': spec['release'], 'products': published}, indent=2))
    print('Published:', json.dumps(published))
    print('Existing checkout fulfillment mappings verified. No customer order or production charge created.')


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--validate', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    asyncio.run(execute('validate' if args.validate else 'apply' if args.apply else 'dry-run'))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(re.sub(r'https?://\S+', '[URL omitted]', str(exc)), file=sys.stderr)
        sys.exit(1)
