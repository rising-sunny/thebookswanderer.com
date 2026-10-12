#!/usr/bin/env python3
"""Follow Lulu print jobs: email tracking to the buyer when a book ships, and
warn the shop inbox when a job needs attention (unpaid, rejected, cancelled).

Each status is noted once on the order ("[lulu] SHIPPED …"), so running this
from cron every couple of hours never repeats an email.

  python scripts/sync_lulu_tracking.py            # check open jobs, act on changes
  python scripts/sync_lulu_tracking.py --dry-run  # print only
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import Order, OrderItem, Product  # noqa: E402
from services import digital, lulu  # noqa: E402
from services import email as email_service  # noqa: E402

ATTENTION = {"UNPAID", "REJECTED", "CANCELED", "ERROR"}


def _noted(order: Order, status: str) -> bool:
    return f"[lulu] {status}" in (order.notes or "")


def _note(order: Order, line: str) -> None:
    prev = (order.notes or "").strip()
    order.notes = (prev + "\n" + line).strip()[-2000:]


async def main() -> int:
    dry = "--dry-run" in sys.argv
    if not lulu.configured():
        print("Lulu keys not set")
        return 1
    db = SessionLocal()
    orders = (
        db.query(Order)
        .filter(Order.lulu_job_id != "", Order.status.notin_(["shipped", "refunded", "cancelled"]))
        .all()
    )
    print(f"{len(orders)} open Lulu job(s)")
    for order in orders:
        if _noted(order, "SHIPPED"):
            continue
        try:
            job = await lulu.request("GET", f"/print-jobs/{order.lulu_job_id}/")
        except lulu.LuluError as exc:
            print(f"  order {order.id}: {exc} {exc.payload}")
            continue
        status = ((job.get("status") or {}).get("name") or "").upper()
        lines = job.get("line_items") or []
        print(f"  order {order.id} job {order.lulu_job_id}: {status}")
        if dry or not status:
            continue

        if status == "SHIPPED":
            line = next((ln for ln in lines if ln.get("tracking_id") or ln.get("tracking_urls")), lines[0] if lines else {})
            number = line.get("tracking_id") or ""
            urls = line.get("tracking_urls") or []
            carrier = line.get("carrier_name") or ""
            _note(order, f"[lulu] SHIPPED {carrier} {number} {urls[0] if urls else ''}".strip())
            items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
            products = {p.id: p for p in db.query(Product).filter(Product.id.in_([i.product_id for i in items]))}
            # Only the book ships here; an order that also holds CJ or
            # Printify items stays open until those ship too.
            others = [i for i in items
                      if products.get(i.product_id)
                      and products[i.product_id].supplier not in (lulu.SUPPLIER, digital.SUPPLIER)]
            if not others:
                order.status = "shipped"
            db.commit()
            books = [i for i in items if getattr(products.get(i.product_id), "supplier", "") == lulu.SUPPLIER]
            try:
                sent = await email_service.send_order_shipped(
                    order, books, tracking_number=number, tracking_url=urls[0] if urls else "", carrier=carrier
                )
                print(f"    shipped {carrier} {number}; email {'sent' if sent else 'not sent'}")
            except Exception as exc:  # noqa: BLE001
                print(f"    shipped, but the email failed: {exc}")
        elif status in ATTENTION and not _noted(order, status):
            msgs = (job.get("status") or {}).get("messages") or {}
            _note(order, f"[lulu] {status} {msgs}"[:400])
            db.commit()
            to = email_service._alert_to()
            if to:
                await email_service.send_email(
                    to=to,
                    subject=f"⚠️ Lulu job {order.lulu_job_id} for order #{order.id}: {status}",
                    text=(f"Order #{order.id} ({order.email}) — Lulu print job {order.lulu_job_id} is {status}.\n"
                          f"{msgs}\n\nUNPAID: add or fix the card at lulu.com (Account > Payment).\n"
                          f"REJECTED/CANCELED: check the job at developers.lulu.com and refund or re-order."),
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
