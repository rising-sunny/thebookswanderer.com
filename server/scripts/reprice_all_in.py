#!/usr/bin/env python3
"""Re-price the catalogue so shipping is included and checkout charges none.

Shipping barely scales with quantity but varies a lot by weight, so the
allowance is per product: the worst freight across the markets we actually
advertise in, marked up like the site used to charge it, grossed up for the
PayPal cut, then rounded to .99.

  python scripts/reprice_all_in.py --dry-run     # show the table, touch nothing
  python scripts/reprice_all_in.py               # apply
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# Markets the ads target. Cheaper destinations simply yield extra margin.
REFERENCE_MARKETS = ("US", "GB", "AU")
QPS_DELAY = 1.3


def _round99(value: float) -> float:
    return math.floor(value) + 0.99


async def worst_freight(cj, product, vid: str) -> float | None:
    """Highest freight across the reference markets, or None if unquotable."""
    worst = 0.0
    seen = False
    for country in REFERENCE_MARKETS:
        try:
            options = await cj.freight_calculate(
                start_country=(product.from_country or "CN").upper(),
                end_country=country,
                products=[{"vid": vid, "quantity": 1}],
            )
        except Exception:  # noqa: BLE001
            options = []
        await asyncio.sleep(QPS_DELAY)
        if not options:
            continue
        cheapest = min(float(o.get("logisticPrice") or 0) for o in options)
        if cheapest > 0:
            seen = True
            worst = max(worst, cheapest)
    return worst if seen else None


async def main() -> int:
    ap = argparse.ArgumentParser(description="Re-price catalogue with shipping included")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from database import SessionLocal, init_db
    from models import Product
    from services import cj

    markup = float(os.getenv("SHIPPING_MARKUP", "1.15"))
    paypal_pct = float(os.getenv("PAYPAL_FEE_PCT", "0.0349"))

    init_db()
    db = SessionLocal()
    changed = 0
    try:
        products = (
            db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all()
        )
        print(
            "%-30s %8s %8s %9s %9s"
            % ("product", "now", "freight", "allowance", "all-in")
        )
        print("-" * 70)

        for product in products:
            variants = product.active_variants()
            vid = ""
            if variants:
                vid = variants[0].cj_vid or ""
            vid = vid or (product.cj_vid or "")
            if not vid:
                print("%-30s  skipped: no CJ variant id" % product.slug[:30])
                continue

            freight = await worst_freight(cj, product, vid)
            if freight is None:
                print("%-30s  skipped: no freight quote" % product.slug[:30])
                continue

            # Gross up for the PayPal cut so the allowance survives the fee.
            allowance = (freight * markup) / (1 - paypal_pct)
            base = float(product.price_usd or 0)
            all_in = _round99(base + allowance)

            print(
                "%-30s %8.2f %8.2f %9.2f %9.2f"
                % (product.slug[:30], base, freight, allowance, all_in)
            )

            if args.dry_run:
                continue

            delta = all_in - base
            product.price_usd = all_in
            # Variants keep their spread: a dearer variant stays dearer.
            for variant in product.variants or []:
                variant.price_usd = _round99(float(variant.price_usd or base) + delta)
            changed += 1

        if args.dry_run:
            print("\n[dry-run] nothing written")
        else:
            db.commit()
            print(f"\nupdated {changed} products (variants shifted by the same delta)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
