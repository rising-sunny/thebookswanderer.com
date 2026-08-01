"""
Server-side purchase events for /admin/live.

Browser tracking covers pageviews and funnel steps; paid confirmation is
recorded here after PayPal capture so sales count even if the buyer closes
the tab before the success page loads.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import SessionLocal
from models import LiveEvent

logger = logging.getLogger("tbw.live_events")


def record_purchase(
    *,
    label: str = "paypal",
    uniq_key: Any,
    value: Optional[float] = None,
    product_slug: Optional[str] = None,
    customer_email: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Insert a purchase event. Idempotent per (label, uniq_key)."""
    sid = f"srv_{label}_{uniq_key}"[:64]
    db = SessionLocal()
    try:
        already = (
            db.query(LiveEvent.id)
            .filter(LiveEvent.session_id == sid, LiveEvent.event_type == "purchase")
            .first()
        )
        if already:
            return
        payload_blob = None
        if extra is not None or customer_email:
            payload_blob = json.dumps(
                {
                    **(extra or {}),
                    **({"email": customer_email} if customer_email else {}),
                }
            )[:2000]
        ev = LiveEvent(
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
            session_id=sid,
            event_type="purchase",
            path=f"/srv/{label}",
            ua_class="server",
            source=label.lower()[:60],
            medium="server",
            product_slug=(product_slug or "")[:120] or None,
            value_usd=float(value) if value is not None else None,
            payload=payload_blob,
        )
        db.add(ev)
        db.commit()
    except Exception:
        logger.exception("record_purchase failed label=%s uniq=%s", label, uniq_key)
        db.rollback()
    finally:
        db.close()
