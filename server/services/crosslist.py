"""Cross-listing between the store and the Etsy shop (with Printify twins).

A Printify product belongs to one Printify shop, so a product sold on both
channels is a pair of twins: one in the store's shop (PRINTIFY_SHOP_ID, used
by checkout) and one in the Etsy-connected shop (PRINTIFY_ETSY_SHOP_ID, which
Printify publishes to Etsy and receives Etsy orders in). Same blueprint,
provider, variants and artwork; the store row keeps both ids.

Digital, Lulu and Prodigi items have no twin: the store makes a draft from an
Etsy listing (files are uploaded at /admin/digital/), or an Etsy draft listing
from a store product.
"""
from __future__ import annotations

import html
import json
import os
import re
from typing import Any

import httpx

from services import digital, etsy, printify


class CrossListError(Exception):
    pass


def etsy_shop_id() -> str:
    return (os.getenv("ETSY_SHOP_ID") or "").strip()


def printify_etsy_shop_id() -> str:
    return (os.getenv("PRINTIFY_ETSY_SHOP_ID") or "").strip()


def _need(value: str, name: str) -> str:
    if not value:
        raise CrossListError(f"{name} is not set in the store .env")
    return value


def _text(value: Any) -> str:
    """Etsy sends HTML entities; the store keeps plain text."""
    return html.unescape(str(value or "")).strip()


def _money(price: dict | None) -> float:
    price = price or {}
    try:
        return round(int(price["amount"]) / int(price.get("divisor") or 100), 2)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return 0.0


# ── Etsy ──────────────────────────────────────────────────────────────


async def _etsy(method: str, path: str, **kwargs) -> Any:
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            headers = {"x-api-key": etsy.api_key(), "Authorization": "Bearer " + await etsy.access_token(client)}
            response = await client.request(method, etsy.BASE + path, headers=headers, **kwargs)
    except httpx.HTTPError:
        raise CrossListError("Etsy unavailable") from None
    except etsy.EtsyError as exc:
        raise CrossListError(str(exc)) from None
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400:
        message = data.get("error") if isinstance(data, dict) else ""
        raise CrossListError(f"Etsy {method} {path.split('?')[0]}: HTTP {response.status_code} {message}".strip())
    return data


async def etsy_listing(listing_id: str) -> dict:
    listing = await _etsy("GET", f"/application/listings/{listing_id}?includes=Images")
    if str(listing.get("shop_id") or "") != _need(etsy_shop_id(), "ETSY_SHOP_ID"):
        raise CrossListError("That listing is not in the connected Etsy shop")
    if (listing.get("price") or {}).get("currency_code", "USD") != "USD":
        raise CrossListError("Only USD listings can be copied")
    inventory = await _etsy("GET", f"/application/listings/{listing_id}/inventory")
    variants = []
    for row in inventory.get("products") or []:
        offer = next((o for o in row.get("offerings") or [] if o.get("is_enabled", True)), None)
        if not offer or row.get("is_deleted"):
            continue
        name = " / ".join(", ".join(map(_text, p.get("values") or [])) for p in row.get("property_values") or [])
        variants.append({"name": name or "Standard", "price_usd": _money(offer.get("price"))})
    images = [i.get("url_fullxfull") for i in sorted(listing.get("images") or [], key=lambda i: i.get("rank", 0))]
    return {
        "listing_id": str(listing.get("listing_id") or listing_id),
        "title": _text(listing.get("title"))[:300],
        "description": _text(listing.get("description")),
        "price_usd": _money(listing.get("price")),
        "is_digital": listing.get("listing_type") == "download" or bool(listing.get("is_digital")),
        "images": [u for u in images if u][:16],
        "variants": variants or [{"name": "Standard", "price_usd": _money(listing.get("price"))}],
        "url": listing.get("url") or "",
    }


async def create_etsy_draft(fields: dict, images: list[str], file_path: Any = None) -> str:
    """Draft listing (not visible on Etsy) with its photos and, for downloads, the file."""
    shop = _need(etsy_shop_id(), "ETSY_SHOP_ID")
    listing = await _etsy("POST", f"/application/shops/{shop}/listings", data=fields)
    listing_id = str(listing.get("listing_id") or "")
    if not listing_id:
        raise CrossListError("Etsy did not return a listing id")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for rank, url in enumerate(images[:10], 1):
            try:
                image = await client.get(url)
            except httpx.HTTPError:
                continue
            if image.status_code == 200 and image.headers.get("content-type", "").startswith("image/"):
                await _etsy("POST", f"/application/shops/{shop}/listings/{listing_id}/images",
                            files={"image": (f"image-{rank}.jpg", image.content, image.headers["content-type"])},
                            data={"rank": str(rank)})
    if file_path:
        await _etsy("POST", f"/application/shops/{shop}/listings/{listing_id}/files",
                    files={"file": (file_path.name, file_path.read_bytes(), "application/octet-stream")},
                    data={"name": file_path.name})
    return listing_id


# ── Printify twins ────────────────────────────────────────────────────


async def _printify(method: str, path: str, body: Any = None) -> Any:
    try:
        return await printify._request(method, path, body)
    except printify.PrintifyError as exc:
        errors = exc.payload.get("errors") if isinstance(exc.payload, dict) else None
        detail = f" {json.dumps(errors)[:300]}" if errors else ""
        raise CrossListError(f"Printify {method} {path.split('?')[0]}: {exc}{detail}") from None
    except httpx.HTTPError:
        raise CrossListError("Printify unavailable") from None


async def printify_for_listing(listing_id: str) -> dict | None:
    """The Etsy-shop Printify product published as this listing, if any."""
    shop = _need(printify_etsy_shop_id(), "PRINTIFY_ETSY_SHOP_ID")
    for page in range(1, 21):
        data = await _printify("GET", f"/shops/{shop}/products.json?page={page}&limit=50")
        for row in data.get("data") or []:
            if str((row.get("external") or {}).get("id") or "") == listing_id:
                return row
        if page >= int(data.get("last_page") or 1):
            return None
    return None


def twin_payload(source: dict, *, title: str | None = None, description: str | None = None,
                 price_usd: float | None = None, prices: dict[int, float] | None = None) -> dict:
    """A create body that rebuilds `source` (same blueprint, provider, variants, artwork)."""
    variants = []
    for v in source.get("variants") or []:
        cents = v.get("price")
        if price_usd is not None:
            cents = round(price_usd * 100)
        elif prices and v.get("id") in prices:
            cents = round(prices[v["id"]] * 100)
        variants.append({"id": v["id"], "price": int(cents or 0), "is_enabled": bool(v.get("is_enabled"))})
    areas = []
    for area in source.get("print_areas") or []:
        areas.append({
            "variant_ids": area.get("variant_ids") or [],
            # Printify lists empty positions (e.g. calendar grids) but rejects them on create
            "placeholders": [
                {"position": ph.get("position"),
                 "images": [{k: img[k] for k in ("id", "x", "y", "scale", "angle") if k in img}
                            for img in ph["images"]]}
                for ph in area.get("placeholders") or [] if ph.get("images")
            ],
        })
    return {
        "title": (title if title is not None else source.get("title") or "")[:140],
        "description": description if description is not None else (source.get("description") or ""),
        "blueprint_id": source["blueprint_id"],
        "print_provider_id": source["print_provider_id"],
        "variants": variants,
        "print_areas": areas,
        "tags": source.get("tags") or [],
    }


async def get_printify(shop: str, product_id: str) -> dict:
    return await _printify("GET", f"/shops/{shop}/products/{product_id}.json")


async def create_twin(shop: str, payload: dict) -> dict:
    return await _printify("POST", f"/shops/{shop}/products.json", payload)


async def update_twin(shop: str, product_id: str, payload: dict) -> dict:
    body = {k: payload[k] for k in ("title", "description", "variants", "tags")}
    return await _printify("PUT", f"/shops/{shop}/products/{product_id}.json", body)


async def publish_twin_to_etsy(product_id: str) -> None:
    shop = _need(printify_etsy_shop_id(), "PRINTIFY_ETSY_SHOP_ID")
    await _printify("POST", f"/shops/{shop}/products/{product_id}/publish.json", {
        "title": True, "description": True, "images": True, "variants": True,
        "tags": True, "keyFeatures": True, "shipping_template": True,
    })


def printify_variants(product: dict) -> list[dict]:
    return [
        {"name": _text(v.get("title")) or "Standard", "printify_variant_id": int(v["id"]),
         "cost_usd": round(int(v.get("cost") or 0) / 100, 2), "price_usd": round(int(v.get("price") or 0) / 100, 2)}
        for v in product.get("variants") or [] if v.get("is_enabled")
    ][:100]


def plain_html(text: str) -> str:
    """Printify descriptions are HTML; keep paragraphs."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)


def digital_file(product: Any) -> Any:
    return digital.file_path(digital.file_for(product, None))


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
