#!/usr/bin/env python3
"""Rewrite already-published pins whose copy has gone stale.

Pin descriptions embed the price, so a catalogue re-price leaves every live
pin advertising a number we no longer charge. This rebuilds each pin's copy
from current product data and PATCHes only what actually changed.

  python scripts/pinterest_refresh_pins.py --dry-run
  python scripts/pinterest_refresh_pins.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

QPS_DELAY = 1.0


async def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh stale Pinterest pin copy")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from database import SessionLocal, init_db
    from models import PinterestPin, Product
    from services import pinterest as pin

    if not pin.is_configured():
        print("Pinterest is not configured")
        return 1

    init_db()
    db = SessionLocal()
    updated = skipped = failed = 0
    try:
        rows = (
            db.query(PinterestPin)
            .filter(PinterestPin.status == "active", PinterestPin.pin_id != "")
            .order_by(PinterestPin.id)
            .all()
        )
        for row in rows:
            product = (
                db.query(Product)
                .filter(Product.slug == row.product_slug, Product.active.is_(True))
                .first()
            )
            if not product:
                print(f"  {row.pin_id}  {row.product_slug}: product gone, left alone")
                skipped += 1
                continue

            wanted = pin.product_pin_payload(product.to_detail())
            # Preserve the campaign the pin was created under.
            try:
                live = await pin.api_request("GET", f"/pins/{row.pin_id}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {row.pin_id}  {row.product_slug}: read failed — {exc}"[:150])
                failed += 1
                continue
            await asyncio.sleep(QPS_DELAY)

            body: dict = {}
            if (live.get("description") or "") != wanted["description"]:
                body["description"] = wanted["description"]
            if (live.get("title") or "") != wanted["title"]:
                body["title"] = wanted["title"]

            if not body:
                print(f"  {row.pin_id}  {row.product_slug}: already current")
                skipped += 1
                continue

            print(f"  {row.pin_id}  {row.product_slug}")
            for field, value in body.items():
                print(f"      old {field}: {(live.get(field) or '')[-70:]}")
                print(f"      new {field}: {value[-70:]}")

            if args.dry_run:
                continue

            try:
                await pin.api_request("PATCH", f"/pins/{row.pin_id}", json=body)
                updated += 1
            except Exception as exc:  # noqa: BLE001
                print(f"      PATCH failed — {exc}"[:200])
                failed += 1
            await asyncio.sleep(QPS_DELAY)

        verb = "would update" if args.dry_run else "updated"
        print(f"\n{verb} {updated if not args.dry_run else '—'} | "
              f"unchanged {skipped} | failed {failed} | total {len(rows)}")
    finally:
        db.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
