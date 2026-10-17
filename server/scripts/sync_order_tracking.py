#!/usr/bin/env python3
"""Follow every supplier leg of open orders (CJ, Printify, Lulu).

When a leg ships, the buyer gets the shipped email for the items in that leg
(carrier, tracking number, link); the order turns "shipped" once every leg
has. When a leg needs a hand (CJ order still unpaid, Printify order on hold,
a cancelled or rejected job) the shop inbox gets one alert.

Each leg's status is noted once on the order ("[cj:123] SHIPPED …"), so cron
can run this every couple of hours without repeating an email.

  python scripts/sync_order_tracking.py            # check, email, update
  python scripts/sync_order_tracking.py --dry-run  # print only
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import Order, OrderItem, Product  # noqa: E402
from services import cj, digital, lulu, printify  # noqa: E402
from services import email as email_service  # noqa: E402

# A CJ order is created unpaid (CJ_PAY_TYPE=3) and a Printify one on hold
# (PRINTIFY_AUTO_PRODUCTION=0) on purpose; only nag once they have waited.
GRACE = timedelta(hours=24)
# Older open orders were handled by hand before this existed; a shipped email
# weeks after delivery would only confuse the buyer.
MAX_AGE = timedelta(days=45)
OPEN = ("cj_submitted", "paid")


@dataclass
class Leg:
    supplier: str          # cj | printify | lulu
    ref: str               # supplier order / job id
    items: list = field(default_factory=list)
    status: str = ""       # normalised: SHIPPED, WAITING, PROBLEM, OTHER
    raw: str = ""          # supplier's own status word
    carrier: str = ""
    number: str = ""
    url: str = ""
    help: str = ""

    @property
    def tag(self) -> str:
        return f"[{self.supplier}:{self.ref}]"


def track_url(number: str) -> str:
    return f"https://t.17track.net/en#nums={number}" if number else ""


def legs_for(order: Order, items: list[OrderItem], products: dict[int, Product]) -> list[Leg]:
    def sup(i):
        return getattr(products.get(i.product_id), "supplier", "") or "cj"

    legs: list[Leg] = []
    if order.cj_order_id:
        cj_items = [i for i in items if sup(i) == "cj"]
        parts = [p.split(":", 1) for p in order.cj_order_id.split(",") if p]
        if all(len(p) == 2 for p in parts):  # split by warehouse: "CN:id,US:id"
            for origin, ref in parts:
                legs.append(Leg("cj", ref, [i for i in cj_items
                                            if (products[i.product_id].from_country or "CN").upper() == origin]))
        else:
            legs.append(Leg("cj", order.cj_order_id, cj_items))
    if order.printify_order_id:
        legs.append(Leg("printify", order.printify_order_id, [i for i in items if sup(i) == "printify"]))
    if order.lulu_job_id:
        legs.append(Leg("lulu", order.lulu_job_id, [i for i in items if sup(i) == lulu.SUPPLIER]))
    return legs


def all_legs_submitted(order, items, products) -> bool:
    """A shipped leg cannot hide another supplier that never accepted its lines."""
    suppliers = {getattr(products.get(i.product_id), 'supplier', '') or 'cj' for i in items}
    if 'lulu' in suppliers and not order.lulu_job_id:
        return False
    if 'printify' in suppliers and not order.printify_order_id:
        return False
    if 'cj' in suppliers:
        if not order.cj_order_id:
            return False
        parts = [p.split(':', 1) for p in order.cj_order_id.split(',') if p]
        if all(len(p) == 2 for p in parts):
            origins = {(products[i.product_id].from_country or 'CN').upper() for i in items
                       if (getattr(products.get(i.product_id), 'supplier', '') or 'cj') == 'cj'}
            if not origins.issubset({origin for origin, ref in parts if ref}):
                return False
    return True


async def check_cj(leg: Leg) -> None:
    d = await cj.get_order(leg.ref)
    leg.raw = str(d.get("orderStatus") or "").upper()
    leg.number = str(d.get("trackNumber") or "")
    leg.carrier = str(d.get("logisticName") or "")
    leg.url = str(d.get("trackingUrl") or "") or track_url(leg.number)
    if leg.raw in ("SHIPPED", "DELIVERED") and leg.number:
        leg.status = "SHIPPED"
    elif leg.raw in ("CREATED", "IN_CART", "UNPAID"):
        leg.status, leg.help = "WAITING", "Pay it in CJ (My CJ > Orders > Unpaid) so it ships."
    elif leg.raw in ("CANCELLED", "CANCELED"):
        leg.status, leg.help = "PROBLEM", "CJ cancelled it: re-order or refund the buyer."
    else:
        leg.status = "OTHER"


async def check_printify(leg: Leg) -> None:
    d = await printify.get_order(leg.ref)
    leg.raw = str(d.get("status") or "").lower()
    shipments = [s for s in (d.get("shipments") or []) if s.get("number")]
    if shipments:
        s = shipments[0]
        leg.carrier, leg.number = str(s.get("carrier") or ""), str(s.get("number") or "")
        leg.url = str(s.get("url") or "") or track_url(leg.number)
    if leg.raw in ("fulfilled", "partially-fulfilled", "shipped") and shipments:
        leg.status = "SHIPPED"
    elif leg.raw in ("on-hold", "pending"):
        leg.status, leg.help = "WAITING", "Send it to production in Printify (Orders > On hold)."
    elif leg.raw in ("canceled", "cancelled", "has-issues", "payment-not-received"):
        leg.status, leg.help = "PROBLEM", "Open the order in Printify and fix the issue or refund the buyer."
    else:
        leg.status = "OTHER"


async def check_lulu(leg: Leg) -> None:
    d = await lulu.request("GET", f"/print-jobs/{leg.ref}/")
    st = d.get("status") or {}
    leg.raw = str(st.get("name") or "").upper()
    lines = d.get("line_items") or []
    line = next((ln for ln in lines if ln.get("tracking_id")), lines[0] if lines else {})
    leg.number = str(line.get("tracking_id") or "")
    urls = line.get("tracking_urls") or []
    leg.url = urls[0] if urls else track_url(leg.number)
    leg.carrier = str(line.get("carrier_name") or "")
    if leg.raw == "SHIPPED":
        leg.status = "SHIPPED"
    elif leg.raw == "UNPAID":
        leg.status, leg.help = "WAITING", "Review the job and pay it manually in the Lulu Print Job portal. Keep automatic and batch payments disabled."
    elif leg.raw in ("REJECTED", "CANCELED", "ERROR"):
        leg.status, leg.help = "PROBLEM", f"Check the job at developers.lulu.com, then re-order or refund. {st.get('messages') or ''}"
    else:
        leg.status = "OTHER"


CHECK = {"cj": (check_cj, cj.is_configured), "printify": (check_printify, printify.configured),
         "lulu": (check_lulu, lulu.configured)}


def noted(order: Order, text: str) -> bool:
    return text in (order.notes or "")


def note(order: Order, line: str) -> None:
    prev = (order.notes or "").strip()
    order.notes = (prev + "\n" + line).strip()[-2000:]


async def alert(order: Order, leg: Leg) -> None:
    to = email_service._alert_to()
    if not to:
        return
    await email_service.send_email(
        to=to,
        subject=f"⚠️ Order #{order.id}: {leg.supplier} {leg.ref} is {leg.raw}",
        text=(f"Order #{order.id} ({order.email}, {order.grand_total:.2f} USD) — {leg.supplier} order {leg.ref} "
              f"is {leg.raw}.\nItems: {', '.join(i.title for i in leg.items) or '—'}\n\n{leg.help}"),
    )


async def main() -> int:
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    from services.paypal_recovery import recover_pending
    from main import _complete_paypal_order
    report = await recover_pending(db, _complete_paypal_order, dry_run=dry)
    print("PayPal recovery: " + json.dumps(report, sort_keys=True))
    since = datetime.utcnow() - MAX_AGE
    orders = (db.query(Order).filter(Order.status.in_(OPEN), Order.created_at >= since)
              .order_by(Order.id).all())
    print(f"{datetime.utcnow():%Y-%m-%d %H:%M} {len(orders)} open order(s)")
    for order in orders:
        items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        products = {p.id: p for p in db.query(Product).filter(Product.id.in_([i.product_id for i in items]))}
        legs = legs_for(order, items, products)
        if not legs:
            continue
        for leg in legs:
            if noted(order, f"{leg.tag} SHIPPED"):
                leg.status = "SHIPPED"
                continue
            check, configured = CHECK[leg.supplier]
            if not configured():
                print(f"  #{order.id} {leg.tag}: {leg.supplier} not configured")
                continue
            try:
                await check(leg)
            except Exception as exc:  # noqa: BLE001
                print(f"  #{order.id} {leg.tag}: lookup failed: {exc} {getattr(exc, 'payload', '') or ''}")
                continue
            print(f"  #{order.id} {leg.tag}: {leg.raw or '?'} → {leg.status} {leg.carrier} {leg.number}".rstrip())
            if dry:
                continue
            if leg.status == "SHIPPED":
                note(order, f"{leg.tag} SHIPPED {leg.carrier} {leg.number} {leg.url}".strip())
                db.commit()
                try:
                    sent = await email_service.send_order_shipped(
                        order, leg.items, tracking_number=leg.number, tracking_url=leg.url, carrier=leg.carrier)
                    print(f"    shipped email {'sent' if sent else 'not sent'}")
                except Exception as exc:  # noqa: BLE001
                    print(f"    shipped email failed: {exc}")
            elif leg.status in ("WAITING", "PROBLEM") and not noted(order, f"{leg.tag} {leg.raw}"):
                if leg.status == "WAITING" and datetime.utcnow() - order.created_at < GRACE:
                    continue
                note(order, f"{leg.tag} {leg.raw}")
                db.commit()
                await alert(order, leg)
                print("    alert sent to the shop inbox")
        # Downloads need no shipping; the order is done once every leg shipped.
        if not dry and all_legs_submitted(order, items, products) and all(leg.status == "SHIPPED" for leg in legs):
            order.status = "shipped"
            db.commit()
            print(f"  #{order.id}: all legs shipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
