"""Refresh only the two reviewed Color the Classics descriptions.

Dry run by default; --apply commits both changes together. Existing prices,
files, variants, images, suppliers and activation state are never assigned.
Rejects an unreviewed existing description instead of replacing merchant edits.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
from dotenv import load_dotenv
load_dotenv(SERVER / '.env')
from database import SessionLocal
from models import Product
from services.shipping import description

TARGETS = {'color-the-classics': 'digital', 'color-the-classics-printed': 'lulu'}

def reviewed_changes(db, specs):
    changes = []
    for slug, supplier in TARGETS.items():
        matching = [s for s in specs if s['slug'] == slug]
        if len(matching) != 1:
            raise ValueError(f'Expected exactly one reviewed spec: {slug}')
        spec = matching[0]
        if spec.get('supplier', 'digital') != supplier:
            raise ValueError(f'Unexpected source supplier: {slug}')
        product = db.query(Product).filter_by(slug=slug).one_or_none()
        if product is None or product.supplier != supplier:
            raise ValueError(f'Existing product/supplier mismatch: {slug}')
        new = description(spec['description'], supplier)
        # The SEO introduction precedes the previously published description.
        old_body = description(spec['description'].split('\n\n', 1)[1], supplier)
        current = description(product.description or '', supplier)
        if current not in (old_body, new):
            raise ValueError(f'Existing copy has unreviewed edits: {slug}')
        changes.append((product, new))
    return changes

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    specs = json.loads(Path(__file__).with_name('digital_products.json').read_text())
    with SessionLocal() as db:
        changes = reviewed_changes(db, specs)
        for product, new in changes:
            print(json.dumps({'slug':product.slug, 'changed':product.description != new,
                              'apply':args.apply}))
            if args.apply:
                product.description = new
        if args.apply:
            db.commit()
        else:
            db.rollback()

if __name__ == '__main__':
    main()
