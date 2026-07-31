"""Import CJYD2171610 — Silicone page-clip bookmarks (text-free images preferred)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal, init_db
from models import Product, ProductVariant
from services import pricing as pricing_service

PID = "2410250803091604000"
SLUG = "silicone-page-clip-bookmark"
TITLE = "Silicone Page Clip Bookmark"
CATEGORY = "Reading Accessories"
DESCRIPTION = (
    "A soft silicone clip that holds your place and rides along as you turn pages. "
    "Gentle on paper, easy to spot on a stack of books — pick a single color or the "
    "six-pack for the whole reading corner."
)

# Clean ambient shots only (no marketing overlays / packaging copy)
HERO = "https://oss-cf.cjdropshipping.com/product/2024/10/25/08/abb58e7c-6c1c-4b30-ac05-96ee2efaef4d_trans.jpeg"

LIFESTYLE = [
    HERO,
    # Magazine in hands — green clip
    "https://oss-cf.cjdropshipping.com/product/2024/10/25/08/28908d4e-bded-4fdb-9e72-2f001394c009_trans.jpeg",
    # Carrying notebooks — yellow clip
    "https://oss-cf.cjdropshipping.com/product/2024/10/25/08/36c3a003-5e45-44d4-a0ca-03e47021bdf5_trans.jpeg",
    # Under-arm book + yellow clip
    "https://oss-cf.cjdropshipping.com/product/2024/10/25/08/a5ef020c-d07a-4f91-aac4-0b7b3025b194_trans.jpeg",
    # Close-up yellow flex on page edge
    "https://oss-cf.cjdropshipping.com/product/2024/10/25/08/2fef0c18-aa62-4818-99c0-cdc92819ecf4_trans.jpeg",
    # All six colors on white (product beauty, no text)
    "https://cf.cjdropshipping.com/quick/product/bd9aab52-26ad-472e-bfaf-cea7e2977d9e.jpg",
]

# White-bg color thumbs (no captions). 6-pack uses clean group shot — NOT retail packaging.
VARIANTS = [
    {
        "vid": "2410250803091604200",
        "sku": "CJYD217161001AZ",
        "name": "Orange",
        "cost": 0.69,
        "image": "https://cf.cjdropshipping.com/quick/product/7742541a-6ac1-4a83-9a60-a842a9ddd9d5.jpg",
    },
    {
        "vid": "2410250803091604300",
        "sku": "CJYD217161002BY",
        "name": "Pink",
        "cost": 0.69,
        "image": "https://cf.cjdropshipping.com/quick/product/63caaa38-89ad-4607-b65c-47ea3e113941.jpg",
    },
    {
        "vid": "2410250803091604400",
        "sku": "CJYD217161003CX",
        "name": "Yellow",
        "cost": 0.69,
        "image": "https://cf.cjdropshipping.com/quick/product/18836130-3f78-489d-ad4d-305d813114ff.jpg",
    },
    {
        "vid": "2410250803091604600",
        "sku": "CJYD217161004DW",
        "name": "Blue",
        "cost": 0.69,
        "image": "https://cf.cjdropshipping.com/quick/product/f366f785-131c-4c8f-bb6c-e141c6251a6a.jpg",
    },
    {
        "vid": "2410250803091604700",
        "sku": "CJYD217161005EV",
        "name": "Green",
        "cost": 0.69,
        "image": "https://cf.cjdropshipping.com/quick/product/2efb886f-a16d-45b3-a382-13140af0390c.jpg",
    },
    {
        "vid": "2410250803091604800",
        "sku": "CJYD217161006FU",
        "name": "Rose",
        "cost": 0.69,
        "image": "https://cf.cjdropshipping.com/quick/product/02a73d31-6c6b-43ac-ac55-84f48272bbad.jpg",
    },
    {
        "vid": "2410250803091604900",
        "sku": "CJYD217161007GT",
        "name": "6-Pack · All Colors",
        "cost": 2.88,
        # CJ default is packaging with Chinese/English text — use clean group instead
        "image": "https://cf.cjdropshipping.com/quick/product/bd9aab52-26ad-472e-bfaf-cea7e2977d9e.jpg",
    },
]


def main() -> None:
    init_db()
    db = SessionLocal()

    product = db.query(Product).filter(Product.slug == SLUG).first()
    if not product:
        product = (
            db.query(Product)
            .filter(Product.cj_pid == PID, Product.active.is_(True))
            .first()
        )
    if not product:
        product = Product(slug=SLUG)
        db.add(product)
    else:
        product.slug = SLUG

    default = VARIANTS[0]
    default_price = pricing_service.retail_from_cost(default["cost"])

    product.title = TITLE
    product.description = DESCRIPTION
    product.image_url = HERO
    product.gallery_json = json.dumps(LIFESTYLE)
    product.details_html = ""
    product.category = CATEGORY
    product.cj_pid = PID
    product.cj_vid = default["vid"]
    product.cj_sku = default["sku"]
    product.cost_usd = default["cost"]
    product.price_usd = default_price
    product.from_country = "CN"
    product.video_url = ""
    product.video_poster = ""
    product.active = True
    db.flush()

    for old in list(product.variants or []):
        db.delete(old)
    db.flush()

    for i, v in enumerate(VARIANTS):
        price = pricing_service.retail_from_cost(v["cost"])
        db.add(
            ProductVariant(
                product_id=product.id,
                name=v["name"],
                cj_vid=v["vid"],
                cj_sku=v["sku"],
                image_url=v["image"],
                cost_usd=v["cost"],
                price_usd=price,
                sort_order=i,
                active=True,
            )
        )
        print(f"  {v['name']}: cost ${v['cost']:.2f} → ${price:.2f}")

    # Display range: min single → 6-pack
    prices = [pricing_service.retail_from_cost(v["cost"]) for v in VARIANTS]
    product.price_usd = min(prices)

    db.commit()
    db.refresh(product)
    print(
        "OK",
        product.id,
        product.slug,
        "variants",
        len(product.active_variants()),
        f"display ${product.price_usd:.2f}–${max(prices):.2f}",
    )
    db.close()


if __name__ == "__main__":
    main()
