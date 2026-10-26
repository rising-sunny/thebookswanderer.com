"""Slant 3D print farm (API v2) for 3D printed products.

SLANT3D_API_KEY (sl_...) is sent as a Bearer token. SLANT3D_PLATFORM_ID names the
platform that files and orders belong to; it is created once on the Slant 3D
account page. Orders are charged to the account card when they are processed,
so the pass-through keeps POST /orders behind TBW_SUPPLIER_ORDERS_ENABLED.

Store and Etsy orders use the reviewed manifest scripts/slant3d_products.json:
only its files and filaments can become an order line, and a draft is processed
(charged) only with SLANT3D_ORDERS_ENABLED and when its cost fits the manifest cap.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import httpx

BASE = "https://slant3dapi.com/v2/api"
SUPPLIER = "slant3d"
MANIFEST = Path(__file__).resolve().parents[1] / "scripts" / "slant3d_products.json"
ORDER_ID = r"SLANT_[0-9]{6,20}"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


class Slant3DError(RuntimeError):
    """Safe operational message; no upstream bodies or credentials."""


def key() -> str:
    value = (os.getenv("SLANT3D_API_KEY") or "").strip()
    if not value or "\n" in value or "\r" in value:
        raise Slant3DError("Slant 3D is not configured")
    return value


def configured() -> bool:
    try:
        return bool(key())
    except Slant3DError:
        return False


def platform_id() -> str:
    return (os.getenv("SLANT3D_PLATFORM_ID") or "").strip()


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer " + key(), "User-Agent": "TheBooksWanderer"}


def enabled() -> bool:
    return os.getenv("SLANT3D_ORDERS_ENABLED", "").lower() in {"1", "true", "yes"}


def ready() -> bool:
    return configured() and bool(platform_id()) and enabled()


def spec() -> dict:
    return json.loads(MANIFEST.read_text())


def product_spec(slug: str) -> dict:
    for item in spec()["products"]:
        if item["slug"] == slug:
            return item
    raise Slant3DError("Unreviewed Slant 3D product")


def by_listing(listing_id) -> dict | None:
    return next((p for p in spec()["products"] if p.get("etsy_listing_id") and str(p["etsy_listing_id"]) == str(listing_id)), None)


def variant_spec(slug: str, sku: str = "") -> dict:
    """The reviewed variant by SKU; a product with a single variant needs none."""
    variants = product_spec(slug)["variants"]
    if not sku and len(variants) == 1:
        return variants[0]
    for v in variants:
        if v["sku"] == sku:
            return v
    raise Slant3DError("Unreviewed Slant 3D variant")


def lines(slug: str, quantity: int, sku: str = "") -> list[dict]:
    """Order lines for one product: one PRINT item per part, from the manifest only."""
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 10:
        raise Slant3DError("Invalid quantity")
    return [{"type": "PRINT", "quantity": quantity, "publicFileServiceId": part["file"],
             "filamentId": part["filament"], "name": part["name"], "SKU": part["sku"]}
            for part in variant_spec(slug, sku)["parts"]]


def customer(name, line1, line2, city, state, zip_code, country) -> dict:
    """Slant mails status updates to the customer email, so the shop's own inbox is used."""
    email = (os.getenv("SLANT3D_CONTACT_EMAIL") or "").strip()
    fields = [name, line1, city, zip_code, country]
    if not email or not all(str(x or "").strip() for x in fields):
        raise Slant3DError("Complete name, street, city, postal code and country are required")
    if country.upper() not in spec()["shipping"]["countries"]:
        raise Slant3DError("Slant 3D does not ship to this destination yet")
    return {"details": {"email": email, "address": {
        "name": name.strip(), "line1": line1.strip(), "line2": (line2 or "").strip(), "city": city.strip(),
        "state": (state or "").strip(), "zip": zip_code.strip(), "country": country.upper()}}}


def draft_payload(ref: str, items: list[dict], cust: dict) -> dict:
    return {"platformId": platform_id(), "customer": cust, "items": items, "metadata": {"tbw_ref": ref}}


def max_cost(slugs_qty, country: str) -> float:
    """What the shop accepts to pay Slant for these lines, from the reviewed manifest."""
    key = "max_cost_us" if country.upper() == "US" else "max_cost_intl"
    return round(sum(product_spec(slug)[key] * qty for slug, qty in slugs_qty), 2)


def shipping(items, country: str) -> dict:
    """Checkout leg. US shipping is in the price; elsewhere a flat rate per order."""
    rates = spec()["shipping"]
    if country.upper() not in rates["countries"]:
        raise Slant3DError("Slant 3D delivery unavailable")
    for product, variant, qty in items:
        lines(product.slug, qty, variant.cj_sku if variant else "")
    total = 0.0 if country.upper() == "US" else float(rates["international"])
    return {"supplier": SUPPLIER, "from": "Print on demand", "logistic_name": "Slant 3D Standard",
            "shipping_total": total, "eta_days": rates.get("eta_days")}


async def request(method: str, path: str, payload=None, *, transport=None) -> dict:
    read = method == "GET" and bool(re.fullmatch("/orders/" + ORDER_ID, path))
    draft = method == "POST" and path == "/orders"
    process = method == "POST" and bool(re.fullmatch("/orders/" + ORDER_ID, path))
    if not (read or draft or process) or (process and not enabled()):
        raise Slant3DError("Slant 3D operation disabled")
    try:
        async with httpx.AsyncClient(timeout=40, follow_redirects=False, transport=transport) as client:
            response = await client.request(method, BASE + path, headers=headers(), json=payload)
        if response.status_code not in (200, 201):
            raise Slant3DError("Slant 3D request failed: HTTP " + str(response.status_code))
        data = response.json()
        order = data.get("data", {}).get("order") if isinstance(data, dict) else None
        if not isinstance(order, dict):
            order = data.get("data") if isinstance(data, dict) else None
        if not isinstance(order, dict) or not re.fullmatch(ORDER_ID, str(order.get("publicId", ""))):
            raise ValueError()
    except (httpx.HTTPError, ValueError, AttributeError):
        raise Slant3DError("Slant 3D unavailable or invalid response") from None
    return order


def cost(order: dict) -> float:
    try:
        total = float(order.get("printingCost") or 0) + float(order.get("deliveryCost") or 0)
    except (TypeError, ValueError):
        raise Slant3DError("Invalid Slant 3D cost") from None
    if not math.isfinite(total) or total <= 0:
        raise Slant3DError("Invalid Slant 3D cost")
    return round(total, 2)


def tracking(order: dict) -> tuple[str, str, str]:
    """Carrier, number and link from an order's fulfillment block, whatever its exact keys."""
    found = {}
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                key = k.lower().replace("_", "")
                if isinstance(v, (str, int)) and str(v).strip():
                    if key in ("trackingnumber", "trackingcode", "tracking") and "number" not in found:
                        found["number"] = str(v).strip()
                    elif key in ("carrier", "carriername", "shippingcarrier", "provider") and "carrier" not in found:
                        found["carrier"] = str(v).strip()
                    elif key in ("trackingurl", "trackinglink", "url") and str(v).startswith("https://") and "url" not in found:
                        found["url"] = str(v).strip()
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(order.get("fulfillment") or {})
    walk({k: v for k, v in order.items() if k in ("tracking_number", "trackingNumber", "carrier")})
    return found.get("carrier", ""), found.get("number", ""), found.get("url", "")
