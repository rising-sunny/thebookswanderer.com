"""Find existing Lulu jobs for paid web orders without creating or paying jobs.

Default: read-only aggregate report. --apply restores verified local job IDs.
This never captures PayPal payments, sends customer email or schedules a worker.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from database import SessionLocal
from models import Order, OrderItem, Product
from services import lulu_submission


async def run(apply=False):
    counts = {'checked': 0, 'matched': 0, 'no_match': 0, 'held': 0, 'applied': 0}
    with SessionLocal() as db:
        orders = db.query(Order).filter(
            Order.status.in_(('paid', 'cj_submitted')),
            Order.lulu_job_id == '',
        ).order_by(Order.id).all()
        for order in orders:
            rows = db.query(OrderItem, Product).join(Product, OrderItem.product_id == Product.id).filter(
                OrderItem.order_id == order.id, Product.supplier == 'lulu'
            ).all()
            if not rows:
                continue
            counts['checked'] += 1
            lines = [{'external_id': f'tbw-{order.id}-{item.id}', 'quantity': item.quantity,
                      'pod_package_id': product.lulu_package} for item, product in rows]
            try:
                matched = await lulu_submission.reconcile(db, order, lines, apply=apply)
            except Exception:
                db.rollback()
                counts['held'] += 1
                continue
            counts['matched' if matched else 'no_match'] += 1
            counts['applied'] += int(bool(matched and apply))
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.apply))))
