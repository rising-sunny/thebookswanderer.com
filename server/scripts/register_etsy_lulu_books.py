#!/usr/bin/env python3
"""Register the store's Lulu books that have an Etsy listing with the Etsy → Lulu worker.

The worker (/opt/etsy_lulu_fulfill/lulu_books/unified, cron every 15 min) prints paid
Etsy book orders at Lulu. It only takes books registered through the MathRelaxing
bridge (codex-api.mathrelaxing.store): print PDFs uploaded to its /files store,
Lulu validations of both files, and a listing that already matches the book.

For each active Lulu product with an etsy_listing_id this script:
  1. checks the Etsy listing (title, price, shipping profile, 3+ images) and, with
     --send, sets its single SKU and the Lulu production partner if missing;
  2. uploads interior and cover to the bridge and validates them at Lulu;
  3. posts the registration, asking the worker to activate the draft once accepted.

  python scripts/register_etsy_lulu_books.py            # report only, changes nothing
  python scripts/register_etsy_lulu_books.py --send     # do it (MATHRELAXING_BRIDGE_TOKEN set)
  python scripts/register_etsy_lulu_books.py --send 36  # one product id

Progress is kept in data/etsy_lulu_registrations.json so a rerun resumes and never
uploads, validates or registers twice. Etsy orders are only printed after the
worker reports the request as active or registered.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import Product  # noqa: E402
from services import crosslist, digital, lulu  # noqa: E402

BRIDGE = "https://codex-api.mathrelaxing.store"
SHOP = 66586766
LULU_PARTNER = 5702394
STATE = ROOT / "data" / "etsy_lulu_registrations.json"


def _load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def _save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


async def _bridge(method: str, path: str, *, key: str, **kwargs) -> dict:
    token = os.environ.get("MATHRELAXING_BRIDGE_TOKEN", "")
    if not token:
        raise SystemExit("MATHRELAXING_BRIDGE_TOKEN is not set")
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": key, **kwargs.pop("headers", {})}
    async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
        r = await client.request(method, BRIDGE + path, headers=headers, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"bridge {method} {path}: HTTP {r.status_code} {r.text[:300]}")
    return r.json()


async def check_listing(p: Product, sku: str, price: float, send: bool) -> list[str]:
    """What still keeps the listing from passing the worker's checks."""
    lid = p.etsy_listing_id
    listing = await crosslist._etsy("GET", f"/application/listings/{lid}?includes=Images")
    problems = []
    if listing.get("shop_id") != SHOP or listing.get("listing_type") != "physical":
        problems.append("not a physical listing of the shop")
    if listing.get("state") not in ("draft", "active"):
        problems.append(f"state is {listing.get('state')}")
    amount = listing.get("price") or {}
    if round(amount.get("amount", 0) / (amount.get("divisor") or 1), 2) != price:
        problems.append(f"Etsy price differs from {price:.2f}")
    if not listing.get("shipping_profile_id"):
        problems.append("no shipping profile")
    if len(listing.get("images") or []) < 3:
        problems.append("fewer than 3 images")
    if problems:
        return problems
    partners = [x.get("production_partner_id") for x in listing.get("production_partners") or []]
    if LULU_PARTNER not in partners:
        if not send:
            return ["Lulu production partner missing (set with --send)"]
        await crosslist._etsy("PATCH", f"/application/shops/{SHOP}/listings/{lid}",
                              data={"production_partner_ids": str(LULU_PARTNER)})
    inventory = await crosslist._etsy("GET", f"/application/listings/{lid}/inventory")
    products = [x for x in inventory.get("products") or [] if not x.get("is_deleted")]
    if len(products) != 1 or len(products[0].get("offerings") or []) != 1:
        return ["listing must have exactly one variant"]
    if products[0].get("sku") != sku:
        if not send:
            return [f"SKU {sku} not set (set with --send)"]
        offering = products[0]["offerings"][0]
        new_offering = {"price": price, "quantity": offering.get("quantity") or 999, "is_enabled": True}
        if offering.get("readiness_state_id"):
            new_offering["readiness_state_id"] = offering["readiness_state_id"]
        await crosslist._etsy("PUT", f"/application/listings/{lid}/inventory",
                              json={"products": [{"sku": sku, "property_values": [], "offerings": [new_offering]}]})
    return []


async def validate(kind: str, url: str, package: str, pages: int | None) -> dict:
    payload = {"source_url": url, "pod_package_id": package}
    if kind == "cover":
        payload["interior_page_count"] = pages
    record = await lulu.request("POST", f"/validate-{kind}/", payload)
    for _ in range(90):
        result = await lulu.request("GET", f"/validate-{kind}/{record['id']}/")
        status = result.get("status")
        if status == "ERROR":
            errors = re.sub(r"https?://\S+", "[url]", str(result.get("errors", [])))
            raise ValueError(f"Lulu rejected the {kind}: {errors}")
        if status == "NORMALIZED":
            if kind == "interior" and package.replace(".", "") not in [
                    x.replace(".", "") for x in result.get("valid_pod_package_ids") or []]:
                raise ValueError(f"package {package} does not fit this interior")
            return {"id": record["id"], "page_count": result.get("page_count")}
        await asyncio.sleep(10)
    raise TimeoutError(f"Lulu {kind} validation still pending; rerun to resume")


async def register(p: Product, state: dict, send: bool) -> str:
    variant = p.default_variant()
    files = {"interior": digital.file_path(digital.file_for(p, variant)),
             "cover": digital.file_path((variant.print_cover if variant else "") or "")}
    if not (p.lulu_package and files["interior"] and files["cover"]):
        return "skipped: Lulu package or print files missing"
    sku = ("TBW-" + p.slug.upper())[:32]
    price = round(variant.price_usd if variant else p.price_usd, 2)
    problems = await check_listing(p, sku, price, send)
    if problems:
        return "not ready: " + "; ".join(problems)
    if not send:
        return f"ready: listing {p.etsy_listing_id}, SKU {sku}, ${price:.2f}"
    entry = state.setdefault(str(p.id), {})
    for kind, path in files.items():
        sha = _sha256(path)
        if entry.get(kind, {}).get("sha256") != sha:
            uploaded = await _bridge("POST", "/files", key="tbw-pdf-" + sha[:48], content=path.read_bytes(),
                                     headers={"Content-Type": "application/pdf"})
            if uploaded.get("sha256") != sha:
                raise RuntimeError(f"bridge stored a different {kind} file")
            entry[kind] = {"sha256": sha, "url": uploaded["url"]}
            _save_state(state)
    for kind in ("interior", "cover"):
        if "validation_id" not in entry[kind]:
            pages = entry["interior"].get("page_count")
            checked = await validate(kind, entry[kind]["url"], p.lulu_package, pages)
            entry[kind]["validation_id"] = checked["id"]
            if kind == "interior":
                entry[kind]["page_count"] = int(checked["page_count"])
            _save_state(state)
    listing = await crosslist._etsy("GET", f"/application/listings/{p.etsy_listing_id}")
    body = {
        "etsy_shop_id": SHOP, "listing_id": int(p.etsy_listing_id),
        "etsy_title": html.unescape(listing["title"]), "sku": sku, "price_usd": price,
        "validation_ids": {k: entry[k]["validation_id"] for k in ("interior", "cover")},
        "activate_listing": listing.get("state") == "draft",
        "book": {
            "title": p.title[:140], "pod_package_id": p.lulu_package.replace(".", ""),
            "page_count": entry["interior"]["page_count"], "enabled": True, "allowed_skus": [sku],
            "interior_url": entry["interior"]["url"], "cover_url": entry["cover"]["url"],
            "interior_sha256": entry["interior"]["sha256"], "cover_sha256": entry["cover"]["sha256"],
        },
    }
    key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:32]
    result = await _bridge("POST", "/api/catalog/lulu/books", key=key, json=body)
    entry["request_id"] = key
    _save_state(state)
    return f"registration {result.get('status')} (request {key}); the worker checks it within 15 min"


async def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--send"]
    send = "--send" in sys.argv
    state = _load_state()
    with SessionLocal() as db:
        query = db.query(Product).filter(Product.supplier == lulu.SUPPLIER, Product.active == 1)
        if args:
            query = query.filter(Product.id.in_([int(a) for a in args]))
        for p in query.order_by(Product.id).all():
            if not p.etsy_listing_id:
                print(f"{p.id} {p.slug}: not on Etsy")
                continue
            try:
                print(f"{p.id} {p.slug}: {await register(p, state, send)}")
            except Exception as exc:  # report and continue with the next book
                print(f"{p.id} {p.slug}: error: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
