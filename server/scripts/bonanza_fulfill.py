#!/usr/bin/env python3
"""Paid Bonanza orders for our print-on-demand listings -> supplier drafts awaiting approval.

Runs with the tracking service (needs the bonanza gateway socket group). For each paid,
unshipped order since bonanza_skus.json "since": a Printify order on hold and/or a Slant 3D
draft are made (nothing charged) and the owner gets an email to approve at /admin/bonanza/.
Approved orders are marked shipped on Bonanza once the suppliers ship.

With "live": false in bonanza_skus.json (or --dry-run) it only logs what it would do;
logs never include the buyer's name or address.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal, init_db  # noqa: E402
from models import BonanzaOrder  # noqa: E402
from services import bonanza, printify, slant3d  # noqa: E402
from services import bonanza_orders as flow  # noqa: E402
from services import email as email_service  # noqa: E402

ADMIN_URL = "https://thebookswanderer.com/admin/bonanza/"


async def alert(subject: str, text: str) -> None:
    to = email_service._alert_to()
    if to:
        await email_service.send_email(to=to, subject=subject, text=text)


def describe(row: BonanzaOrder) -> str:
    s = json.loads(row.summary_json or "{}")
    lines = "\n".join(f"  {i['quantity']} x {i['title'] or i['sku']} {i['options'] or ''}".rstrip() for i in s.get("items", []))
    return f"Bonanza order {s.get('order_id')} to {s.get('country')} (paid {s.get('total') or '?'})\n{lines}"


async def main() -> int:
    cfg = flow.config()
    dry = "--dry-run" in sys.argv or not cfg.get("live")
    try:
        data = await bonanza.call("/getOrdersRequest", {"orderRole": "seller", "soldTimeFrom": cfg["since"],
                                                         "paginationInput": {"entriesPerPage": 100, "pageNumber": 1}})
    except bonanza.BonanzaError as exc:
        print(f"Bonanza orders unavailable: {exc}")
        return 0
    orders = [o for o in bonanza.orders(data) if bonanza.order_id(o)]
    print(f"Bonanza: {len(orders)} orders since {cfg['since']}{' (dry run)' if dry else ''}")
    init_db()
    db = SessionLocal()
    for order in orders:
        ref = "bonanza-" + bonanza.order_id(order)
        if not bonanza.is_paid(order) or bonanza.is_shipped(order) or db.get(BonanzaOrder, ref):
            continue
        if dry:
            try:
                legs = [flow.resolve(cfg, l) for l in bonanza.items(order)]
                print(f"  {ref}: would prepare {[(l['supplier'], l['sku'], l['quantity']) for l in legs]}")
            except ValueError as exc:
                print(f"  {ref}: would go to review: {exc}; shape {json.dumps(bonanza.shape(order))[:1500]}")
            continue
        row = await flow.prepare(db, cfg, order)
        print(f"  {ref}: {row.state} {row.note}".rstrip())
        if row.state == "awaiting":
            over = row.cost_usd > row.max_cost > 0
            await alert(f"🛒 Bonanza order {ref}: approve to print ({row.cost_usd:.2f} USD)",
                        f"{describe(row)}\n\nSupplier cost: {row.cost_usd:.2f} USD"
                        f"{' (above the usual ' + format(row.max_cost, '.2f') + ')' if over else ''}.\n"
                        f"Nothing has been charged yet. Approve or leave it at {ADMIN_URL}")
        elif row.state == "review":
            await alert(f"⚠️ Bonanza order {ref} needs you", f"{describe(row)}\n\n{row.note}\n\n"
                        f"It was not sent to any supplier. Handle it by hand, then mark it at {ADMIN_URL}")
    if not dry:
        for row in db.query(BonanzaOrder).filter_by(state="approved").all():
            try:
                done = await flow.sync(db, row)
            except (printify.PrintifyError, slant3d.Slant3DError, bonanza.BonanzaError) as exc:
                print(f"  {row.ref}: tracking lookup failed: {exc}")
                continue
            if done:
                print(f"  {row.ref}: shipped, {done.split(' ', 1)[0]}")
                if done.startswith("manual"):
                    await alert(f"📦 Bonanza order {row.ref} shipped: add tracking by hand",
                                f"{describe(row)}\n\nTracking: {done.split(' ', 1)[1]}\n"
                                f"Bonanza did not accept the update ({row.note}); mark it shipped in your booth.")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
