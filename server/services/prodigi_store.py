"""Storefront Prodigi transport; separate from the quotes-only evaluation client.

Only the reviewed local product manifest can become a quote/order line. Live
orders require the explicit runtime flag and a paid local submission claim.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://api.prodigi.com/v4.0'
SUPPLIER = 'prodigi'
MANIFEST = ROOT / 'scripts/prodigi_phyllotaxis.json'

class ProdigiError(RuntimeError):
    """Safe operational message; no upstream bodies, URLs or credentials."""


def spec():
    return json.loads(MANIFEST.read_text())


def key():
    filename = os.getenv('PRODIGI_API_KEY_FILE', '')
    if not filename and os.getenv('CREDENTIALS_DIRECTORY'):
        filename = str(Path(os.environ['CREDENTIALS_DIRECTORY']) / 'prodigi_api_key')
    try:
        value = Path(filename).read_text().strip() if filename else os.getenv('PRODIGI_API_KEY', '').strip()
    except OSError:
        raise ProdigiError('Prodigi credential unavailable') from None
    if not value or '\n' in value or '\r' in value:
        raise ProdigiError('Prodigi credential unavailable')
    return value


def configured():
    try:
        return bool(key())
    except ProdigiError:
        return False


def enabled():
    return os.getenv('PRODIGI_ORDERS_ENABLED', '').lower() in {'1', 'true', 'yes'}


def asset_path(name=None):
    data = spec()
    name = data['artwork_file'] if name is None else name
    if name != data['artwork_file'] or Path(name).name != name:
        raise ProdigiError('Unknown artwork')
    path = Path(os.getenv('PRODIGI_ARTWORK_DIR', '/var/lib/tbw-prodigi/artwork')) / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != data['artwork_sha256']:
        raise ProdigiError('Reviewed artwork is unavailable or changed')
    return path


def _asset_sig(name):
    secret = os.getenv('SECRET_KEY', '')
    if not secret:
        raise ProdigiError('Artwork signing unavailable')
    return hmac.new(secret.encode(), ('prodigi-artwork:' + name).encode(), hashlib.sha256).hexdigest()


def asset_url(base):
    name = spec()['artwork_file']
    asset_path(name)
    return base.rstrip('/') + '/api/prodigi/artwork/' + quote(name) + '?sig=' + _asset_sig(name)


def check_asset_signature(name, signature):
    try:
        return name == spec()['artwork_file'] and bool(signature) and hmac.compare_digest(_asset_sig(name), signature)
    except ProdigiError:
        return False


def ready():
    try:
        asset_path()
        _asset_sig(spec()['artwork_file'])
        return configured() and enabled()
    except (ProdigiError, OSError, ValueError):
        return False


def quote_line(product, variant, quantity):
    data = spec()
    if product.supplier != SUPPLIER or product.slug != data['slug']:
        raise ProdigiError('Unreviewed Prodigi product')
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 20:
        raise ProdigiError('Invalid quantity')
    if variant and variant.product_id != product.id:
        raise ProdigiError('Variant does not belong to product')
    return {'sku': data['supplier_sku'], 'copies': quantity,
            'attributes': data['attributes'], 'assets': [{'printArea': data['print_area']}]}


async def request(method, path, payload=None, *, transport=None):
    read = method == 'GET' and bool(re.fullmatch(r'/orders/ord_[A-Za-z0-9_-]{1,100}', path))
    product = method == 'GET' and bool(re.fullmatch(r'/products/[A-Za-z0-9_-]{1,100}', path))
    quoting = method == 'POST' and path == '/quotes'
    ordering = method == 'POST' and path == '/orders'
    if not (read or product or quoting or ordering) or (ordering and not enabled()):
        raise ProdigiError('Prodigi operation disabled')
    try:
        async with httpx.AsyncClient(timeout=35, follow_redirects=False, transport=transport) as client:
            response = await client.request(method, BASE + path, headers={'X-API-Key': key()}, json=payload)
        if response.status_code != 200:
            raise ProdigiError('Prodigi request failed: HTTP ' + str(response.status_code))
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
    except (httpx.HTTPError, ValueError):
        raise ProdigiError('Prodigi unavailable or invalid response') from None
    return data


def money(value):
    if not isinstance(value, dict) or value.get('currency') != 'USD':
        raise ProdigiError('Invalid quote currency')
    try:
        amount = float(value['amount'])
    except (ValueError, TypeError, KeyError):
        raise ProdigiError('Invalid quote amount') from None
    if not math.isfinite(amount) or amount < 0:
        raise ProdigiError('Invalid quote amount')
    return amount


async def shipping(items, country):
    if country != 'US' or not ready():
        raise ProdigiError('Prodigi delivery unavailable')
    lines = [quote_line(p, v, q) for p, v, q in items]
    data = await request('POST', '/quotes', {'destinationCountryCode': 'US', 'currencyCode': 'USD',
                         'shippingMethod': 'Standard', 'items': lines})
    if str(data.get('outcome', '')).lower() not in {'created', 'createdwithissues'}:
        raise ProdigiError('Prodigi quote unavailable')
    # Sales-tax warning is documented; it is borne by the shop, not added later to a paid buyer.
    if any(i.get('errorCode') != 'destinationCountryCode.UsSalesTaxWarning' for i in data.get('issues', [])):
        raise ProdigiError('Prodigi quote needs review')
    options = [q for q in data.get('quotes', []) if q.get('shipmentMethod') == 'Standard']
    if len(options) != 1:
        raise ProdigiError('Standard delivery quote unavailable')
    quote_data = options[0]
    costs = quote_data.get('costSummary', {})
    total = money(costs.get('totalCost'))
    shipping_cost = money(costs.get('shipping'))
    retail = sum(float(v.price_usd if v else p.price_usd)*q for p, v, q in items)
    if total > retail*.75:
        raise ProdigiError('Supplier costs require a price review')
    return {'supplier': SUPPLIER, 'from': 'Print on demand', 'logistic_name': 'Prodigi Standard',
            'shipping_total': 0.0,
            'eta_days': None}


def recipient(order):
    if order.shipping_country_code != 'US':
        raise ProdigiError('Prodigi launch supports US destinations only')
    fields = [order.customer_name, order.shipping_address, order.shipping_city,
              order.shipping_province, order.shipping_zip]
    if not all(str(x or '').strip() for x in fields):
        raise ProdigiError('Complete name, street, city, state and ZIP are required')
    return {'name': order.customer_name, 'email': order.email, 'phoneNumber': order.phone or '',
            'address': {'line1': order.shipping_address, 'line2': order.shipping_address2 or '',
                        'postalOrZipCode': order.shipping_zip, 'countryCode': 'US',
                        'townOrCity': order.shipping_city, 'stateOrCounty': order.shipping_province}}


async def product_check():
    data = spec()
    result = await request('GET', '/products/' + data['supplier_sku'])
    product = result.get('product', {})
    if str(result.get('outcome', '')).lower() != 'ok' or product.get('sku') != data['supplier_sku']:
        raise ProdigiError('Product verification failed')
    matches = [v for v in product.get('variants', []) if v.get('attributes') == data['attributes']
               and 'US' in v.get('shipsTo', [])]
    if not matches or not product.get('printAreas', {}).get('default', {}).get('required'):
        raise ProdigiError('Product variant or print area changed')
    expected = {'horizontalResolution': 3600, 'verticalResolution': 4800}
    if any(v.get('printAreaSizes', {}).get('default') != expected for v in matches):
        raise ProdigiError('Product print dimensions changed')
    return True
