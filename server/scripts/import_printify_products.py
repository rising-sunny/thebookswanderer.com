"""List the Printify print-on-demand products on the site (US shipping only).

Reads each product from the Printify shop (variant ids, base cost, mockups),
prices it like the CJ catalogue — margin formula plus the US shipping
allowance folded in — and upserts it with supplier="printify".

  python scripts/import_printify_products.py --dry-run
  python scripts/import_printify_products.py
  python scripts/import_printify_products.py --slug readers-2027-desk-calendar

Needs PRINTIFY_API_TOKEN and PRINTIFY_SHOP_ID in server/.env.
Skip the Pinterest launch pins with PINTEREST_LAUNCH_PIN_ENABLED=0.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import pricing as pricing_service
from services import printify

LOCAL = "/assets/products/printify"

PRODUCTS = [
    {
        "slug": "readers-2027-desk-calendar",
        "printify_id": "6acaf5de8ed76a615a0adea3",
        "title": "Readers — A Desk Calendar for 2027",
        "category": "decor",
        "description": (
            "A desk calendar for 2027 with a print of someone reading for every month: "
            "Dürer's St. Jerome in his study, Whistler's girl by the lamp, Rembrandt, "
            "Fantin-Latour, Menzel, Bellows and others, reproduced from the open-access "
            "collection of the Cleveland Museum of Art, each with a line or two on books "
            "by an old author. Spiral-bound and self-standing, 10 × 5 in on satin paper. "
            "Printed to order in the US; ships to US addresses only."
        ),
        "hero": f"{LOCAL}/readers-2027-cover.jpg",
        "local": [f"{LOCAL}/readers-2027-january.jpg", f"{LOCAL}/readers-2027-june.jpg",
                  f"{LOCAL}/readers-2027-october.jpg"],
        # Printify's back-cover mockup shows the factory's production label
        "skip_mockup_camera": {"100992"},
        # the desk-scene mockup is square and shows the object; the flat
        # cover is 2:1 and floats in the 4:5 product frame
        "hero_mockup_camera": "99193",
        "variant_name": "Desk calendar, 10 × 5 in",
    },
    {
        "slug": "library-ephemera-sticker-sheet",
        "printify_id": "6acaf5e2b55938329c0b2d70",
        "title": "Library Ephemera Sticker Sheet",
        "category": "book-accessories",
        "description": (
            "One sheet of the things you used to find inside a library book: a bookplate "
            "with Dürer's sleeping lion, a date-due slip with crooked stamps, a typed "
            "catalogue card for Pride and Prejudice, three spine labels, a 'Reference only' "
            "stamp and a few more. Kiss-cut glossy vinyl on a 5.8 × 8.3 in sheet, for a "
            "Kindle, a journal or a laptop. Write on the bookplate with a permanent marker; "
            "ballpoint smudges on vinyl. Printed to order in the US; ships to US addresses only."
        ),
        "hero": f"{LOCAL}/library-stickers-sheet.jpg",
        "local": [],
        "skip_mockup_camera": set(),
        "variant_name": "Sticker sheet, 5.8 × 8.3 in",
    },
]


def _round99(v: float) -> float:
    return math.floor(v) + 0.99


async def fetch(spec: dict) -> dict:
    p = await printify._request("GET", f"/shops/{printify.shop_id()}/products/{spec['printify_id']}.json")
    variants = [v for v in p["variants"] if v.get("is_enabled")]
    if len(variants) != 1:
        raise SystemExit(f"{spec['slug']}: expected one enabled variant, got {len(variants)}")
    v = variants[0]
    mockups = [m["src"] for m in p.get("images", [])
               if not any(f"/{cam}/" in m["src"] for cam in spec["skip_mockup_camera"])]
    ship = await printify.shipping_cost(
        [{"product_id": spec["printify_id"], "variant_id": v["id"], "quantity": 1}], "US")
    return {"variant_id": v["id"], "cost": v["cost"] / 100, "ship": ship, "mockups": mockups}


def price(cost: float, ship: float) -> float:
    markup = float(os.getenv("SHIPPING_MARKUP", "1.15"))
    paypal_pct = float(os.getenv("PAYPAL_FEE_PCT", "0.0349"))
    allowance = ship * markup / (1 - paypal_pct)
    return _round99(pricing_service.retail_from_cost(cost) + allowance)


def write(spec: dict, info: dict, retail: float) -> None:
    from database import SessionLocal, init_db
    from models import Product, ProductVariant

    init_db()
    db = SessionLocal()
    product = db.query(Product).filter(Product.slug == spec["slug"]).first()
    if not product:
        product = Product(slug=spec["slug"])
        db.add(product)
    hero = spec["hero"]
    cam = spec.get("hero_mockup_camera")
    scene = next((m for m in info["mockups"] if cam and f"/{cam}/" in m), None)
    if scene:
        hero = scene
    gallery = [hero, *([spec["hero"]] if scene else []), *spec["local"],
               *[m for m in info["mockups"] if m != scene]]
    product.title = spec["title"]
    product.description = spec["description"]
    product.image_url = hero
    product.gallery_json = json.dumps(gallery)
    product.details_html = ""
    product.category = spec["category"]
    product.supplier = "printify"
    product.printify_product_id = spec["printify_id"]
    product.cj_pid = ""
    product.cj_vid = ""
    product.cj_sku = ""
    product.cost_usd = info["cost"]
    product.price_usd = retail
    product.from_country = "US"
    product.video_url = ""
    product.video_poster = ""
    product.active = True
    db.flush()
    for old in list(product.variants or []):
        db.delete(old)
    db.flush()
    db.add(ProductVariant(
        product_id=product.id, name=spec["variant_name"], cj_vid="", cj_sku="",
        printify_variant_id=info["variant_id"], image_url=hero,
        cost_usd=info["cost"], price_usd=retail, sort_order=0, active=True,
    ))
    db.commit()
    db.refresh(product)
    print(f"  OK product {product.id} {product.slug}")
    try:
        from services import pinterest_jobs as pin_jobs

        launch = asyncio.run(pin_jobs.pin_product_launch(db, product))
        print("  pinterest_launch", json.dumps(launch, default=str))
    except Exception as exc:  # noqa: BLE001
        print("  pinterest_launch failed:", exc)
    db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--slug", action="append")
    args = ap.parse_args()
    if not printify.configured():
        raise SystemExit("PRINTIFY_API_TOKEN / PRINTIFY_SHOP_ID missing in server/.env")
    for spec in PRODUCTS:
        if args.slug and spec["slug"] not in args.slug:
            continue
        info = asyncio.run(fetch(spec))
        retail = price(info["cost"], info["ship"])
        print(f"{spec['slug']:34} cost ${info['cost']:.2f}  US ship ${info['ship']:.2f}  "
              f"price ${retail:.2f}  mockups {len(info['mockups'])}")
        if not args.dry_run:
            write(spec, info, retail)


if __name__ == "__main__":
    main()
