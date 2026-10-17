"""Verify canonical PayPal orders before capturing or releasing goods.

The webhook, browser return, and existing tracking worker share this path.
Only awaiting-payment orders are candidates; paid supplier submissions are
never retried here (an ambiguous supplier response requires reconciliation).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from models import Order
from services import paypal

log = logging.getLogger("tbw.paypal")
PAID_STATES = ("paid", "cj_submitted", "fulfilled", "delivered", "shipped")


class InvalidPayment(ValueError):
    pass


class NotApproved(ValueError):
    pass


def _amount_matches(amount: dict, expected: float) -> bool:
    try:
        value = Decimal(str(amount.get("value", "")))
        total = Decimal(str(expected)).quantize(Decimal("0.01"))
        return (amount.get("currency_code") == "USD" and value.is_finite()
                and total.is_finite() and total > 0 and value == total)
    except (InvalidOperation, TypeError, ValueError):
        return False


def validate(data: dict, order: Order, *, captured: bool = False) -> None:
    """Require the stored provider ID, shop reference and exact USD amount."""
    if data.get("id") != order.paypal_order_id or data.get("intent") != "CAPTURE":
        raise InvalidPayment("PayPal order identity or intent mismatch")
    units = data.get("purchase_units") or []
    if len(units) != 1:
        raise InvalidPayment("Unexpected PayPal purchase units")
    unit = units[0]
    custom, reference = unit.get("custom_id"), unit.get("reference_id")
    if ((not custom and not reference) or (custom and custom != f"tbw:{order.id}")
            or (reference and reference != str(order.id))):
        raise InvalidPayment("PayPal shop reference mismatch")
    if not _amount_matches(unit.get("amount") or {}, order.grand_total):
        raise InvalidPayment("PayPal order amount mismatch")
    if captured:
        captures = (unit.get("payments") or {}).get("captures") or []
        if (data.get("status") != "COMPLETED" or len(captures) != 1
                or captures[0].get("status") != "COMPLETED"):
            raise NotApproved("PayPal capture is not completed")
        capture = captures[0]
        if not capture.get("id") or not _amount_matches(capture.get("amount") or {}, order.grand_total):
            raise InvalidPayment("PayPal captured amount mismatch")
        if capture.get("custom_id") and capture["custom_id"] != f"tbw:{order.id}":
            raise InvalidPayment("PayPal capture reference mismatch")


async def confirmed_capture(order: Order) -> dict:
    """Read first. Capture only an approved, matching order; reconcile lost replies."""
    data = await paypal.get_order(order.paypal_order_id)
    validate(data, order)
    if data.get("status") == "APPROVED":
        try:
            # The same request ID is used by the browser, webhook and worker.
            await paypal.capture_order(order.paypal_order_id)
        except Exception:
            # A timeout can mean PayPal accepted the capture. Never infer that
            # the buyer did not pay from the transport error alone.
            data = await paypal.get_order(order.paypal_order_id)
            if data.get("status") != "COMPLETED":
                raise paypal.PayPalError("PayPal capture requires reconciliation") from None
        else:
            # Canonical GET includes purchase-unit amount and all capture data,
            # even if the capture POST returned only a minimal representation.
            data = await paypal.get_order(order.paypal_order_id)
    elif data.get("status") != "COMPLETED":
        raise NotApproved("PayPal order has not been approved")
    validate(data, order, captured=True)
    return data


async def recover_pending(db, complete, *, dry_run: bool = False) -> dict:
    """Fallback in the existing two-hour tracking job; no new daemon or cron.

    Completed payments from the last 30 days can also be recovered. Unapproved
    and expired checkouts stay unpaid. Never retry already-paid supplier work.
    A dry run only counts local candidates and performs no external calls.
    """
    orders = (db.query(Order).filter(Order.status == "awaiting_payment",
              Order.paypal_order_id != "", Order.created_at >= datetime.utcnow() - timedelta(days=30))
              .order_by(Order.id).all())
    report = {"candidates": len(orders), "recovered": 0, "pending": 0, "errors": 0, "dry_run": dry_run}
    if dry_run or not paypal.configured():
        return report
    for order in orders:
        try:
            result = await complete(order, db)
            report["recovered" if result in ("success", "paid_cj_pending") else "pending"] += 1
        except Exception as exc:
            db.rollback()
            report["errors"] += 1
            log.warning("PayPal recovery order %s: %s", order.id, type(exc).__name__)
    return report
