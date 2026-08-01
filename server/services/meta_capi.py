"""
Meta Conversions API — server-side Purchase.

Why this exists: the browser pixel fires Purchase from the PayPal return page,
where only order_id and status are known, so it reaches Meta without a value and
ROAS cannot be computed. Here the captured order is in hand, so the real amount
is sent.

Both events carry the same event_id ("purchase-<order id>"), which is how Meta
deduplicates them — it keeps one conversion, preferring the server event. See
the META_EVENTS bridge in track.js for the browser half.

Configure META_PIXEL_ID and META_CAPI_TOKEN in server/.env (see .env.example).
Unconfigured, every function here no-ops: checkout must never fail because of
analytics.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, Iterable

import httpx

log = logging.getLogger("tbw.meta_capi")

GRAPH_VERSION = "v21.0"
TIMEOUT_SECONDS = 8


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def configured() -> bool:
    return bool(_env("META_PIXEL_ID") and _env("META_CAPI_TOKEN"))


def _hash(value: str | None) -> str | None:
    """SHA-256 of a normalized value, as Meta requires for customer data."""
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _split_name(full_name: str) -> tuple[str | None, str | None]:
    parts = [p for p in (full_name or "").strip().split() if p]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[-1]


def _user_data(order: Any, fbp: str | None, fbc: str | None,
               client_ip: str | None, user_agent: str | None) -> dict:
    """Identifiers Meta uses to match the conversion to a person.

    Everything personal is hashed before it leaves the server; fbp/fbc are
    Meta's own cookie values and are sent raw, as documented.
    """
    first, last = _split_name(getattr(order, "customer_name", "") or "")
    data: dict[str, Any] = {}

    for key, value in (
        ("em", _hash(getattr(order, "email", ""))),
        ("ph", _hash((getattr(order, "phone", "") or "").replace(" ", ""))),
        ("fn", _hash(first)),
        ("ln", _hash(last)),
        ("ct", _hash((getattr(order, "shipping_city", "") or "").replace(" ", ""))),
        ("st", _hash(getattr(order, "shipping_province", ""))),
        ("zp", _hash((getattr(order, "shipping_zip", "") or "").replace(" ", ""))),
        ("country", _hash(getattr(order, "shipping_country_code", ""))),
    ):
        if value:
            data[key] = [value]

    if fbp:
        data["fbp"] = fbp
    if fbc:
        data["fbc"] = fbc
    if client_ip:
        data["client_ip_address"] = client_ip
    if user_agent:
        data["client_user_agent"] = user_agent
    return data


def _custom_data(order: Any, items: Iterable[Any], slugs: dict[int, str]) -> dict:
    contents = []
    num_items = 0
    for item in items:
        quantity = int(getattr(item, "quantity", 1) or 1)
        num_items += quantity
        contents.append(
            {
                # Same identifier the browser pixel sends as content_ids, so
                # both halves of the event agree.
                "id": slugs.get(getattr(item, "product_id", 0)) or str(
                    getattr(item, "product_id", "")
                ),
                "quantity": quantity,
                "item_price": round(float(getattr(item, "unit_price", 0) or 0), 2),
            }
        )

    return {
        # The store charges in USD through PayPal. The ad account is in CLP and
        # Meta converts for reporting, so this must stay the currency actually
        # charged, not the ad account's.
        "currency": "USD",
        "value": round(float(getattr(order, "grand_total", 0) or 0), 2),
        "content_type": "product",
        "content_ids": [c["id"] for c in contents],
        "contents": contents,
        "num_items": num_items,
        "order_id": str(getattr(order, "id", "")),
    }


def event_id_for(order_id: Any) -> str:
    """Shared with the browser pixel so Meta can deduplicate."""
    return f"purchase-{order_id}"


async def send_purchase(
    order: Any,
    items: Iterable[Any],
    slugs: dict[int, str] | None = None,
    *,
    fbp: str | None = None,
    fbc: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    event_source_url: str | None = None,
) -> bool:
    """Send one Purchase. Returns True if Meta accepted it.

    Never raises: a failure here must not affect a paid order.
    """
    if not configured():
        return False

    pixel_id = _env("META_PIXEL_ID")
    payload = {
        "data": [
            {
                "event_name": "Purchase",
                "event_time": int(time.time()),
                "event_id": event_id_for(getattr(order, "id", "")),
                "action_source": "website",
                "event_source_url": event_source_url
                or f"{_env('PUBLIC_BASE_URL', 'https://thebookswanderer.com').rstrip('/')}"
                f"/checkout.html?status=success&order_id={getattr(order, 'id', '')}",
                "user_data": _user_data(order, fbp, fbc, client_ip, user_agent),
                "custom_data": _custom_data(order, items, slugs or {}),
            }
        ]
    }

    test_code = _env("META_CAPI_TEST_CODE")
    if test_code:
        # Routes the event to Events Manager > Test events instead of counting
        # it as production data. Leave unset in production.
        payload["test_event_code"] = test_code

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"https://graph.facebook.com/{GRAPH_VERSION}/{pixel_id}/events",
                params={"access_token": _env("META_CAPI_TOKEN")},
                json=payload,
            )
        if resp.status_code >= 400:
            log.warning("Meta CAPI rejected purchase %s: %s %s",
                        getattr(order, "id", "?"), resp.status_code, resp.text[:400])
            return False
        log.info("Meta CAPI purchase %s sent: %s",
                 getattr(order, "id", "?"), resp.text[:200])
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Meta CAPI purchase %s failed: %s", getattr(order, "id", "?"), exc)
        return False
