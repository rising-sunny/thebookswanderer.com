"""Paid Bonanza orders -> Printify / Slant 3D, charged only after the owner approves.

1. prepare(): freeze the order, then make the supplier drafts. A Printify order created
   through the API stays on hold and a Slant 3D draft is not charged, so nothing is paid yet.
2. approve() (from /admin/bonanza/): Printify send_to_production and Slant processing.
3. sync(): once every leg has shipped, mark the Bonanza order shipped with its tracking.
Orders that cannot be matched to a listing go to "review" and are left to a person.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from models import BonanzaOrder, SlantSubmission
from services import bonanza, printify, slant3d, slant3d_submission

MAP_FILE = Path(__file__).resolve().parent.parent / "scripts" / "bonanza_skus.json"
SLANT_SHIPPED = {"SHIPPED", "DELIVERED"}


def config() -> dict:
    return json.loads(MAP_FILE.read_text())


def resolve(cfg: dict, line: dict) -> dict:
    """One Bonanza line -> one supplier leg; ValueError when it cannot be matched safely."""
    sku, attrs, qty = line["sku"], line["attributes"], line["quantity"]
    if not 1 <= qty <= 10:
        raise ValueError(f"{sku}: quantity {qty}")
    for parent, spec in cfg["products"].items():
        variants = spec["variants"]
        if sku in variants:
            key = sku
        elif sku == parent:
            want = {k.lower(): v.lower() for k, v in attrs.items()}
            key = next((k for k, v in variants.items() if v["attributes"]
                        and all(want.get(n.lower()) == val.lower() for n, val in v["attributes"].items())), None)
            if key is None and len(variants) == 1:
                key = next(iter(variants))
            if key is None:
                raise ValueError(f"{sku}: option {attrs or 'missing'} not recognised")
        else:
            continue
        if spec["supplier"] == "printify":
            return {"supplier": "printify", "sku": key, "quantity": qty, "product_id": spec["product_id"],
                    "variant_id": variants[key]["variant_id"], "cap": float(spec.get("max_cost_us", 0)) * qty}
        return {"supplier": "slant3d", "sku": key, "quantity": qty, "slug": spec["slug"]}
    raise ValueError(f"{sku or 'no SKU'}: not one of our print-on-demand listings")


def _contact() -> str:
    from services import email as email_service
    return (os.getenv("SLANT3D_CONTACT_EMAIL") or (email_service._alert_to() or [""])[0]).strip()


def _printify_address(a: dict) -> dict:
    first, _, last = a["name"].partition(" ")
    return {"first_name": first, "last_name": last or first, "email": _contact(), "country": a["country"],
            "region": printify.region_code(a["state"]), "address1": a["line1"], "address2": a["line2"],
            "city": a["city"], "zip": a["zip"]}


def summary(order: dict, cfg_lines: list[dict]) -> dict:
    a = bonanza.address(order)
    return {"order_id": bonanza.order_id(order), "country": a["country"],
            "items": [{"sku": l["sku"], "quantity": l["quantity"], "title": l["title"],
                       "options": l["attributes"]} for l in cfg_lines],
            "total": str(order.get("total") or order.get("amountPaid") or "")}


async def prepare(db, cfg: dict, order: dict) -> BonanzaOrder:
    """Freeze a paid order once, then make the (free) supplier drafts."""
    ref = "bonanza-" + bonanza.order_id(order)
    row = db.get(BonanzaOrder, ref)
    if row:
        return row
    lines = bonanza.items(order)
    row = BonanzaOrder(ref=ref, summary_json=json.dumps(summary(order, lines)))
    db.add(row)
    try:
        if not lines:
            raise ValueError("the order has no items")
        legs = [resolve(cfg, l) for l in lines]
        a = bonanza.address(order)
        if not all(a[k] for k in ("name", "line1", "city", "zip")) or len(a["country"]) != 2:
            raise ValueError("incomplete shipping address")
    except ValueError as exc:
        row.state, row.note = "review", str(exc)[:300]
        db.commit()
        return row
    row.legs_json = json.dumps(legs)
    db.commit()
    try:
        await make_drafts(db, cfg, row, a)
    except (printify.PrintifyError, slant3d.Slant3DError, ValueError) as exc:
        row.state, row.note = "review", f"draft failed: {exc}"[:300]
        db.commit()
    return row


async def make_drafts(db, cfg: dict, row: BonanzaOrder, a: dict) -> None:
    legs = json.loads(row.legs_json)
    shop = cfg["printify_shop_id"]
    cost = cap = 0.0
    pf = [l for l in legs if l["supplier"] == "printify"]
    if pf:
        oid = pf[0].get("printify_order_id")
        if not oid:
            created = await printify.create_order(
                external_id=row.ref, label=row.ref, address=_printify_address(a), shop=shop,
                lines=[{"product_id": l["product_id"], "variant_id": l["variant_id"], "quantity": l["quantity"]} for l in pf])
            oid = str(created.get("id") or "")
            if not oid:
                raise ValueError("Printify returned no order id")
            for l in pf:
                l["printify_order_id"] = oid
            row.legs_json = json.dumps(legs)
            db.commit()
        detail = await printify.get_order(oid, shop)
        cost += sum(float(detail.get(k) or 0) for k in ("total_price", "total_shipping", "total_tax")) / 100
        cap += sum(l["cap"] for l in pf)
    sl = [l for l in legs if l["supplier"] == "slant3d"]
    if sl:
        if not slant3d.ready():
            raise ValueError("Slant 3D ordering is not enabled on this server")
        claim = db.get(SlantSubmission, row.ref)
        if not claim:
            items = [line for l in sl for line in slant3d.lines(l["slug"], l["quantity"], l["sku"])]
            cust = slant3d.customer(a["name"], a["line1"], a["line2"], a["city"], a["state"], a["zip"], a["country"])
            claim = slant3d_submission.prepare(db, row.ref, slant3d.draft_payload(row.ref, items, cust),
                                               slant3d.max_cost([(l["slug"], l["quantity"]) for l in sl], a["country"]))
        if not claim.draft_id:
            order = await slant3d.request("POST", "/orders", json.loads(claim.payload_json))
            claim.draft_id, claim.cost_usd, claim.state = order["publicId"], slant3d.cost(order), "drafted"
            db.commit()
        cost += claim.cost_usd
        cap += claim.max_cost
    row.cost_usd, row.max_cost, row.state = round(cost, 2), round(cap, 2), "awaiting"
    db.commit()


def _printify_ids(row: BonanzaOrder) -> list[str]:
    return sorted({l["printify_order_id"] for l in json.loads(row.legs_json or "[]") if l.get("printify_order_id")})


async def approve(db, row: BonanzaOrder) -> None:
    """Send the drafts to production. Claimed first, so a double click charges once."""
    taken = db.query(BonanzaOrder).filter_by(ref=row.ref, state="awaiting").update(
        {"state": "approving"}, synchronize_session=False)
    db.commit()
    db.refresh(row)
    if not taken:
        raise ValueError(f"{row.ref} is {row.state}, not awaiting approval")
    shop = config()["printify_shop_id"]
    try:
        for oid in _printify_ids(row):
            await printify.send_to_production(oid, shop)
        claim = db.get(SlantSubmission, row.ref)
        if claim:
            await slant3d_submission.submit(db, claim)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        row = db.get(BonanzaOrder, row.ref)
        row.state, row.note = "review", f"approval stopped: {exc}"[:300]
        db.commit()
        raise ValueError(row.note) from None
    row.state, row.note = "approved", ""
    db.commit()


async def dismiss(db, row: BonanzaOrder) -> None:
    """Leave the order to a person: cancel the on-hold Printify order; a Slant draft costs nothing."""
    if row.state not in {"awaiting", "review"}:
        raise ValueError(f"{row.ref} is {row.state}")
    shop = config()["printify_shop_id"]
    for oid in _printify_ids(row):
        try:
            await printify.cancel_order(oid, shop)
        except printify.PrintifyError:
            pass
    row.state = "dismissed"
    db.commit()


async def sync(db, row: BonanzaOrder) -> str:
    """For an approved order: once every leg has shipped, mark it shipped on Bonanza.
    Returns "" while waiting, or a line describing what happened."""
    shop = config()["printify_shop_id"]
    found = []
    for oid in _printify_ids(row):
        shipments = (await printify.get_order(oid, shop)).get("shipments") or []
        if not shipments:
            return ""
        s = shipments[0]
        found.append((str(s.get("carrier") or ""), str(s.get("number") or ""), str(s.get("url") or "")))
    claim = db.get(SlantSubmission, row.ref)
    if claim:
        order = await slant3d.request("GET", "/orders/" + claim.draft_id)
        if order.get("status") not in SLANT_SHIPPED:
            return ""
        found.append(slant3d.tracking(order))
    found = [f for f in found if f[1]]
    if not found:
        return ""
    carrier, number, _url = found[0]
    order_id = json.loads(row.summary_json).get("order_id", "")
    try:
        await bonanza.call("/completeSaleRequest", {
            "transactionID": order_id, "shipped": True,
            "shipment": {"shippingCarrierUsed": carrier or "Other", "shipmentTrackingNumber": number}},
            key=f"tbw-{row.ref}-shipped")
        row.tracking = f"posted {carrier} {number}".strip()[:300]
        result = "posted"
    except bonanza.BonanzaError as exc:
        row.tracking = f"emailed {carrier} {number}".strip()[:300]
        row.note = str(exc)[:300]
        result = "manual"
    row.state = "shipped"
    db.commit()
    return result + " " + "; ".join(f"{c} {n} {u}".strip() for c, n, u in found)
