"""Once-only Slant 3D orders for store orders and Etsy receipts.

A draft costs nothing, so creating one again after a crash is harmless. Processing
charges the account card: the claim moves drafted -> processing in one UPDATE before
the only POST, and an unclear result becomes "uncertain" until a GET settles it.
A draft whose cost is above the manifest cap is held for review, never processed.
"""
from __future__ import annotations

import json

from models import SlantSubmission
from services import slant3d

DONE = {"PAID", "QUEUED", "PRINTING", "ITEMS_ON_SHELF", "POST_PROCESSING", "COMPLETED", "IN_REVIEW",
        "AWAITING_SHIPMENT", "SHIPPED", "DELIVERED"}


def prepare(db, ref: str, payload: dict, max_cost: float) -> SlantSubmission:
    """Freeze the order once; a second call returns the frozen claim unchanged."""
    claim = db.get(SlantSubmission, ref)
    if claim:
        return claim
    claim = SlantSubmission(ref=ref, payload_json=json.dumps(payload, sort_keys=True), max_cost=max_cost)
    db.add(claim)
    db.commit()
    return claim


async def submit(db, claim: SlantSubmission, *, transport=None) -> str:
    if claim.state == "submitted":
        return claim.draft_id
    if claim.state in {"uncertain", "review", "processing"}:
        raise slant3d.Slant3DError(f"Slant 3D order {claim.ref} is {claim.state}; no duplicate sent")
    if not slant3d.ready():
        raise slant3d.Slant3DError("Slant 3D ordering unavailable")
    if not claim.draft_id:
        order = await slant3d.request("POST", "/orders", json.loads(claim.payload_json), transport=transport)
        claim.draft_id, claim.cost_usd, claim.state = order["publicId"], slant3d.cost(order), "drafted"
        db.commit()
    if claim.cost_usd > claim.max_cost:
        claim.state, claim.error_kind = "review", "cost above cap"
        db.commit()
        raise slant3d.Slant3DError(f"Slant 3D cost {claim.cost_usd:.2f} is above the cap {claim.max_cost:.2f}; held")
    taken = db.query(SlantSubmission).filter_by(ref=claim.ref, state="drafted").update(
        {"state": "processing"}, synchronize_session=False)
    db.commit()
    db.refresh(claim)
    if not taken:
        raise slant3d.Slant3DError(f"Slant 3D order {claim.ref} changed state; no duplicate sent")
    try:
        order = await slant3d.request("POST", "/orders/" + claim.draft_id, transport=transport)
        if order.get("publicId") != claim.draft_id or order.get("status") not in DONE:
            raise slant3d.Slant3DError("Slant 3D processing not confirmed")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        claim = db.get(SlantSubmission, claim.ref)
        claim.state, claim.error_kind = "uncertain", type(exc).__name__[:80]
        db.commit()
        raise slant3d.Slant3DError("Slant 3D result uncertain; it is reconciled before any retry") from None
    claim.state, claim.error_kind = "submitted", ""
    db.commit()
    return claim.draft_id


async def reconcile(db, claim: SlantSubmission, *, transport=None) -> str:
    """GET only. A draft still in DRAFT was never charged and may be processed again."""
    if claim.state != "uncertain" or not claim.draft_id:
        return claim.state
    order = await slant3d.request("GET", "/orders/" + claim.draft_id, transport=transport)
    status = order.get("status")
    if status in DONE:
        claim.state, claim.error_kind = "submitted", ""
    elif status == "DRAFT":
        claim.state = "drafted"
    else:
        claim.state, claim.error_kind = "review", str(status)[:80]
    db.commit()
    return claim.state
