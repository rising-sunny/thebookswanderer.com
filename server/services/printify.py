"""
Printify client (print-on-demand). Products live in the store's own Printify
shop (no sales channel attached); orders are pushed here after PayPal capture.

Env:
  PRINTIFY_API_TOKEN       Personal access token (Printify > Settings > Connections)
  PRINTIFY_SHOP_ID         Shop holding the site's products
  PRINTIFY_AUTO_PRODUCTION "0" (default) leaves paid orders on hold in Printify
                           for a manual look, like CJ_PAY_TYPE=3 does for CJ;
                           "1" sends them straight to production (and charges
                           the card on file in Printify).
Docs: https://developers.printify.com/
"""
from __future__ import annotations

import os
from typing import Any

import httpx

BASE = "https://api.printify.com/v1"

# Printify ships these products from US print providers; selling them abroad
# would cost 2-3x in freight, so the site only offers them in the US.
SHIP_COUNTRIES = {"US"}
ETA_DAYS = "5-10"  # 2-5 days production + 3-5 days US ground

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "puerto rico": "PR",
}


class PrintifyError(RuntimeError):
    def __init__(self, message: str, payload: Any = None):
        super().__init__(message)
        self.payload = payload


def _token() -> str:
    return (os.getenv("PRINTIFY_API_TOKEN") or "").strip()


def shop_id() -> str:
    return (os.getenv("PRINTIFY_SHOP_ID") or "").strip()


def configured() -> bool:
    return bool(_token() and shop_id())


def ships_to(country_code: str) -> bool:
    return (country_code or "").upper() in SHIP_COUNTRIES


def region_code(province: str) -> str:
    p = (province or "").strip()
    if len(p) == 2:
        return p.upper()
    return US_STATES.get(p.lower(), p)


async def _request(method: str, path: str, json_body: dict | None = None) -> Any:
    if not configured():
        raise PrintifyError("PRINTIFY_API_TOKEN / PRINTIFY_SHOP_ID not configured")
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.request(
            method,
            f"{BASE}{path}",
            headers={"Authorization": f"Bearer {_token()}", "User-Agent": "TheBooksWanderer"},
            json=json_body,
        )
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise PrintifyError(f"Invalid JSON from Printify ({resp.status_code})", resp.text) from exc
    if resp.status_code >= 400:
        raise PrintifyError(str(data.get("message") or data.get("error") or resp.status_code), data)
    return data


async def shipping_cost(lines: list[dict], country_code: str) -> float:
    """Standard shipping in USD for [{product_id, variant_id, quantity}]."""
    data = await _request(
        "POST",
        f"/shops/{shop_id()}/orders/shipping.json",
        {"line_items": lines, "address_to": {"country": country_code.upper()}},
    )
    return round(float(data.get("standard") or 0) / 100, 2)


async def create_order(*, external_id: str, label: str, lines: list[dict], address: dict) -> dict:
    return await _request(
        "POST",
        f"/shops/{shop_id()}/orders.json",
        {
            "external_id": external_id,
            "label": label,
            "line_items": lines,
            "shipping_method": 1,
            "send_shipping_notification": False,
            "address_to": address,
        },
    )


async def send_to_production(order_id: str) -> dict:
    return await _request("POST", f"/shops/{shop_id()}/orders/{order_id}/send_to_production.json")


def auto_production() -> bool:
    return (os.getenv("PRINTIFY_AUTO_PRODUCTION", "0") or "").strip().lower() in ("1", "true", "yes", "on")
