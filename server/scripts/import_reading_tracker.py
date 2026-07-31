"""Import CJHD2955749 — Wooden reading tracker (skip Custom; no Chinese watermarks)."""
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

PID = "2070383738680356866"
SLUG = "wooden-reading-tracker"
TITLE = "Wooden Reading Tracker"
CATEGORY = "Reading Accessories"
DESCRIPTION = (
    "A mini wooden bookshelf that keeps count of the books you finish. Flip the "
    "tiles as your stack grows — a small desk keepsake for the year of reading "
    "ahead. Choose the classic plaque or a blank plate to mark as you like."
)

# Ambient shots without Chinese “实物图” watermarks
HERO = "https://cf.cjdropshipping.com/1f00fb9a-0067-4283-b289-8b9d33496ec1.jpg"

LIFESTYLE = [
    HERO,  # café / brick wall — classic plaque
    "https://cf.cjdropshipping.com/b933d910-6992-4a79-8759-4e098c5b7f23.jpg",  # window light
    "https://cf.cjdropshipping.com/d9a2acd7-6201-4dc0-9ca7-2b39e64a98fa.jpg",  # desk + notebook
    "https://cf.cjdropshipping.com/ae5ec3ce-25f4-4b96-acf4-d6d013c2710e.jpg",  # blank + ink & open book
    "https://cf.cjdropshipping.com/18592113-ca6c-4399-b3d9-ba52dfbe5010.jpg",  # desk with lamp
    "https://cf.cjdropshipping.com/39d4e28f-6fa9-44c7-967e-0b00968a560d.jpg",  # close with lavender
    "https://cf.cjdropshipping.com/09bac6e7-6ba8-4b97-9a7a-f9c8b9d47e10.jpg",  # soft side light
]

# Custom Version ($3.18) needs order notes we don't collect yet — omit.
VARIANTS = [
    {
        "vid": "2070383738768437250",
        "sku": "CJHD295574901AZ",
        "name": 'Classic — "My Reading Journey"',
        "cost": 2.07,
        "image": "https://cf.cjdropshipping.com/b933d910-6992-4a79-8759-4e098c5b7f23.jpg",
    },
    {
        "vid": "2070383738768437251",
        "sku": "CJHD295574902BY",
        "name": "Blank plaque",
        "cost": 2.07,
        "image": "https://cf.cjdropshipping.com/9da0dab6-5217-4d09-b997-9058addee5ef.jpg",
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

    product.price_usd = min(
        pricing_service.retail_from_cost(v["cost"]) for v in VARIANTS
    )

    db.commit()
    db.refresh(product)
    print(
        "OK",
        product.id,
        product.slug,
        "variants",
        len(product.active_variants()),
        "price",
        product.price_usd,
    )
    print("NOTE: Custom Version omitted (requires order-note personalization).")
    db.close()


if __name__ == "__main__":
    main()
