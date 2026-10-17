"""PayPal Checkout (Orders v2) — same pattern as mathrelaxing.store."""
from __future__ import annotations

import os
import hashlib

import httpx

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET", "")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "live")

BASE_URL = (
    "https://api-m.paypal.com"
    if PAYPAL_MODE == "live"
    else "https://api-m.sandbox.paypal.com"
)


class PayPalError(RuntimeError):
    pass


def configured() -> bool:
    return bool(PAYPAL_CLIENT_ID and PAYPAL_SECRET)


async def _get_access_token() -> str:
    if not configured():
        raise PayPalError("PAYPAL_CLIENT_ID / PAYPAL_SECRET not configured")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def _payer_action_url(data: dict) -> str:
    for link in data.get("links", []):
        if link.get("rel") == "payer-action":
            return link["href"]
    raise PayPalError(f"PayPal did not return payer-action URL: {data}")


async def create_checkout(
    *,
    order_id: int,
    amount_usd: float,
    description: str,
    return_url: str,
    cancel_url: str,
    brand_name: str = "The Books Wanderer",
) -> tuple[str, str]:
    """Returns (checkout_url, paypal_order_id)."""
    token = await _get_access_token()
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": str(order_id),
                "custom_id": f"tbw:{order_id}",
                "description": description[:120],
                "amount": {
                    "currency_code": "USD",
                    "value": f"{amount_usd:.2f}",
                },
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED",
                    "brand_name": brand_name,
                    "locale": "en-US",
                    # NO_PREFERENCE lets PayPal choose the first screen per buyer:
                    # login for someone with an account, the card form for someone
                    # without one. LOGIN sent everybody to a sign-in wall, and
                    # BILLING would do the reverse and tax returning PayPal users.
                    # Needs "PayPal account optional" on in the merchant profile,
                    # and PayPal still decides per buyer whether guest is offered.
                    "landing_page": "NO_PREFERENCE",
                    "user_action": "PAY_NOW",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                }
            }
        },
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{BASE_URL}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code >= 400:
            raise PayPalError(f"create order failed: {resp.status_code} {resp.text}")
        data = resp.json()

    return _payer_action_url(data), data.get("id") or ""


async def capture_order(paypal_order_id: str) -> dict:
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{BASE_URL}/v2/checkout/orders/{paypal_order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                # Full body, so the caller can check custom_id and amount.
                "Prefer": "return=representation",
                "PayPal-Request-Id": "tbw-cap-" + hashlib.sha256(paypal_order_id.encode()).hexdigest()[:28],
            },
        )
        if resp.status_code >= 400:
            raise PayPalError(f"PayPal capture failed (HTTP {resp.status_code})")
        return resp.json()


async def get_order(paypal_order_id: str) -> dict:
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{BASE_URL}/v2/checkout/orders/{paypal_order_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def verify_webhook(headers, event: dict) -> bool:
    """Ask PayPal to verify its signed event against this store's webhook ID.

    Never download the supplied certificate URL or trust event fields first.
    Verification errors propagate so PayPal can retry a temporary outage.
    """
    fields = {
        "auth_algo": "paypal-auth-algo",
        "cert_url": "paypal-cert-url",
        "transmission_id": "paypal-transmission-id",
        "transmission_sig": "paypal-transmission-sig",
        "transmission_time": "paypal-transmission-time",
    }
    if not PAYPAL_WEBHOOK_ID:
        raise PayPalError("PayPal webhook is not configured")
    if any(not headers.get(h) for h in fields.values()):
        return False
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/v1/notifications/verify-webhook-signature",
            headers={"Authorization": f"Bearer {token}"},
            json={**{key: headers[header] for key, header in fields.items()},
                  "webhook_id": PAYPAL_WEBHOOK_ID, "webhook_event": event},
        )
        resp.raise_for_status()
        return resp.json().get("verification_status") == "SUCCESS"
