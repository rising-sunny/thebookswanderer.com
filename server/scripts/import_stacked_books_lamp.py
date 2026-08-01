"""Import CJJT1868063 — Stacked Books Table Lamp (stained-glass style)."""
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

SPU = "CJJT1868063"
PID = "1712006336982028288"
SLUG = "stacked-books-table-lamp"
TITLE = "Stacked Books Table Lamp"
CATEGORY = "decor"
DESCRIPTION = (
    "Four stacked “books” of stained-glass color that glow into a soft nightstand "
    "light — warm enough for late chapters, pretty enough to leave on by day. "
    "Choose plastic or resin, and a single lamp or a multi-pack for more than one "
    "reading corner."
)

# Clean lifestyle (no pack-count overlays)
HERO = (
    "https://oss-cf.cjdropshipping.com/product/2023/10/11/07/"
    "5a44f8df-8a0c-45f9-8b0d-88d50da4953f.jpg"
)

LIFESTYLE = [
    HERO,  # lit on nightstand
    # Resin glow, handheld close-up
    "https://cf.cjdropshipping.com/quick/product/b26ce999-9705-4cc8-afa7-79e5b8146840.jpg",
    # Daytime nightstand (unlit) with glasses
    "https://oss-cf.cjdropshipping.com/product/2023/10/11/07/"
    "fbb26d01-7989-42f8-ae8d-1af7e88a1868.jpg",
    # Studio angle — plastic finish
    "https://oss-cf.cjdropshipping.com/product/2023/10/11/07/"
    "147f6a2c-2e90-4348-a8ef-16ffce82f6a0.jpg",
    # Studio front — plastic finish
    "https://oss-cf.cjdropshipping.com/product/2023/10/11/07/"
    "ab1e1c3a-ea77-4f08-9a69-0391d7a72d97.jpg",
]

# Clean variant thumbs only (multi-packs reuse single shots — CJ pack shots have "2pc"/"3pc" text)
IMG_PLASTIC = HERO
IMG_RESIN = (
    "https://cf.cjdropshipping.com/quick/product/b26ce999-9705-4cc8-afa7-79e5b8146840.jpg"
)

VARIANTS = [
    {
        "vid": "1712006337120440320",
        "sku": "CJJT186806302BY",
        "name": "Plastic · Single",
        "cost": 3.34,
        "image": IMG_PLASTIC,
    },
    {
        "vid": "1712006337057525760",
        "sku": "CJJT186806301AZ",
        "name": "Resin · Single",
        "cost": 5.03,
        "image": IMG_RESIN,
    },
    {
        "vid": "1717881281515622400",
        "sku": "CJJT186806303CX",
        "name": "Plastic · 2-Pack",
        "cost": 6.60,
        "image": IMG_PLASTIC,
    },
    {
        "vid": "1717881281578536960",
        "sku": "CJJT186806304DW",
        "name": "Resin · 2-Pack",
        "cost": 9.95,
        "image": IMG_RESIN,
    },
    {
        "vid": "1717889843021221888",
        "sku": "CJJT186806305EV",
        "name": "Plastic · 3-Pack",
        "cost": 9.90,
        "image": IMG_PLASTIC,
    },
    {
        "vid": "1717889843088330752",
        "sku": "CJJT186806306FU",
        "name": "Resin · 3-Pack",
        "cost": 14.93,
        "image": IMG_RESIN,
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

    prices: list[float] = []
    for i, v in enumerate(VARIANTS):
        price = pricing_service.retail_from_cost(v["cost"])
        prices.append(price)
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

    product.price_usd = min(prices)
    db.commit()
    db.refresh(product)
    print(
        "OK",
        product.id,
        product.slug,
        "variants",
        len(product.active_variants()),
        f"${min(prices):.2f}–${max(prices):.2f}",
        "category",
        product.category,
        "spu",
        SPU,
    )
    db.close()


if __name__ == "__main__":
    main()
