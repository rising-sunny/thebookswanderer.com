#!/usr/bin/env python3
"""Paid Etsy orders for 3D prints go to Slant 3D; Slant's tracking goes back to Etsy.

Only listings in scripts/slant3d_products.json (etsy_listing_id) are touched, and only
receipts created after SLANT3D_ETSY_SINCE (unix seconds), so older orders are never
printed twice. Each receipt becomes one Slant order through the once-only claim in
services/slant3d_submission.py. Nothing is charged unless SLANT3D_ORDERS_ENABLED=1.

Posting tracking to Etsy needs the transactions_w scope (scripts/etsy_oauth.py);
without it the shop inbox gets the carrier and number to enter by hand.

  python scripts/etsy_slant_fulfill.py            # do it
  python scripts/etsy_slant_fulfill.py --dry-run  # list what would happen
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal, init_db  # noqa: E402
from models import SlantSubmission  # noqa: E402
from services import email as email_service  # noqa: E402
from services import etsy, slant3d, slant3d_submission  # noqa: E402

SHIPPED = {"SHIPPED", "DELIVERED"}


async def etsy_call(client, method, path, **kw):
    headers = {"x-api-key": etsy.api_key(), "Authorization": "Bearer " + await etsy.access_token(client)}
    return await client.request(method, etsy.BASE + path, headers=headers, **kw)


def shop_id() -> str:
    return (os.getenv("ETSY_SHOP_ID") or "").strip()


def receipt_lines(receipt: dict) -> list[tuple[str, int, str]]:
    """(manifest slug, quantity, variant SKU) for each 3D-print line of a receipt."""
    out = []
    for t in receipt.get("transactions") or []:
        product = slant3d.by_listing(t.get("listing_id"))
        if product:
            out.append((product["slug"], int(t.get("quantity") or 1), str(t.get("sku") or "")))
    return out


def payload_for(receipt: dict, wanted) -> tuple[str, dict, float]:
    ref = f"etsy-{receipt['receipt_id']}"
    items = [line for slug, qty, sku in wanted for line in slant3d.lines(slug, qty, sku)]
    cust = slant3d.customer(receipt.get("name", ""), receipt.get("first_line", ""), receipt.get("second_line", ""),
                            receipt.get("city", ""), receipt.get("state", ""), receipt.get("zip", ""),
                            receipt.get("country_iso", ""))
    country = receipt.get("country_iso", "")
    return ref, slant3d.draft_payload(ref, items, cust), slant3d.max_cost([(s, q) for s, q, _ in wanted], country)


async def alert(subject: str, text: str) -> None:
    to = email_service._alert_to()
    if to:
        await email_service.send_email(to=to, subject=subject, text=text)


async def advance(db, claim, dry: bool) -> None:
    """Move one claim forward: settle an unclear charge, then process a draft."""
    before = claim.state
    if dry:
        print(f"  {claim.ref}: {claim.state} (dry run)")
        return
    try:
        if claim.state == "uncertain":
            await slant3d_submission.reconcile(db, claim)
        if claim.state in {"prepared", "drafted"}:
            await slant3d_submission.submit(db, claim)
    except slant3d.Slant3DError as exc:
        print(f"  {claim.ref}: {exc}")
    print(f"  {claim.ref}: {before} -> {claim.state} {claim.draft_id}".rstrip())
    if claim.state in {"review", "uncertain"} and before != claim.state:
        await alert(f"⚠️ Etsy 3D order {claim.ref}: Slant 3D {claim.state}",
                    f"{claim.ref} (Slant {claim.draft_id or 'no draft'}, cost {claim.cost_usd:.2f}, cap {claim.max_cost:.2f}) "
                    f"is {claim.state}: {claim.error_kind}.\nCheck it in the Slant 3D dashboard. Do not create a duplicate order.")


async def post_tracking(client, db, claim, dry: bool) -> None:
    order = await slant3d.request("GET", "/orders/" + claim.draft_id)
    if order.get("status") not in SHIPPED:
        return
    carrier, number, url = slant3d.tracking(order)
    if not number:
        return
    receipt_id = claim.ref.split("-", 1)[1]
    print(f"  {claim.ref}: shipped {carrier} {number}")
    if dry:
        return
    response = await etsy_call(client, "POST", f"/application/shops/{shop_id()}/receipts/{receipt_id}/tracking",
                               json={"tracking_code": number, "carrier_name": carrier or "other", "send_bcc": True})
    if response.status_code == 200:
        claim.tracking = f"posted {carrier} {number}".strip()[:300]
    else:
        claim.tracking = f"emailed {carrier} {number}".strip()[:300]
        await alert(f"📦 Etsy order {receipt_id} shipped: add tracking by hand",
                    f"Slant 3D shipped Etsy receipt {receipt_id} ({claim.draft_id}).\nCarrier: {carrier or '?'}\n"
                    f"Tracking: {number}\n{url}\n\nEtsy refused the update (HTTP {response.status_code}); "
                    "rerun scripts/etsy_oauth.py to grant transactions_w and this becomes automatic.")
    db.commit()


async def main() -> int:
    dry = "--dry-run" in sys.argv
    since = (os.getenv("SLANT3D_ETSY_SINCE") or "").strip()
    listed = [p for p in slant3d.spec()["products"] if p.get("etsy_listing_id")]
    if not listed or not since.isdigit() or not shop_id():
        print("Etsy → Slant 3D: no listing, SLANT3D_ETSY_SINCE or ETSY_SHOP_ID; nothing to do")
        return 0
    if not slant3d.ready():
        print("Etsy → Slant 3D: SLANT3D_ORDERS_ENABLED, key or platform missing; nothing sent")
        dry = True
    init_db()
    db = SessionLocal()
    async with httpx.AsyncClient(timeout=40) as client:
        try:
            response = await etsy_call(client, "GET", f"/application/shops/{shop_id()}/receipts", params={
                "was_paid": "true", "was_canceled": "false", "min_created": since, "limit": 100})
        except (etsy.EtsyError, httpx.HTTPError) as exc:
            print(f"Etsy receipts unavailable: {exc}")
            return 1
        if response.status_code != 200:
            print(f"Etsy receipts: HTTP {response.status_code}")
            return 1
        for receipt in response.json().get("results", []):
            wanted = receipt_lines(receipt)
            if not wanted or receipt.get("is_shipped"):
                continue
            ref = f"etsy-{receipt['receipt_id']}"
            if not db.get(SlantSubmission, ref):
                try:
                    ref, payload, cap = payload_for(receipt, wanted)
                except slant3d.Slant3DError as exc:
                    print(f"  {ref}: {exc}")
                    await alert(f"⚠️ Etsy 3D order {ref} not sent to Slant 3D", f"{exc}. Check the address in Etsy and send it by hand.")
                    continue
                if dry:
                    print(f"  {ref}: would draft {json.dumps([sku for _, _, sku in wanted])}")
                    continue
                slant3d_submission.prepare(db, ref, payload, cap)
        for claim in db.query(SlantSubmission).filter(SlantSubmission.ref.like("etsy-%")).all():
            if claim.state != "submitted":
                await advance(db, claim, dry)
            elif not claim.tracking:
                try:
                    await post_tracking(client, db, claim, dry)
                except (slant3d.Slant3DError, etsy.EtsyError, httpx.HTTPError) as exc:
                    print(f"  {claim.ref}: tracking lookup failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
