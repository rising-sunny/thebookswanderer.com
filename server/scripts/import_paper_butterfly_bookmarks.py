"""Import CJJT1095184 — Paper butterfly & flower bookmark set (14 pcs)."""
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

SPU = "CJJT1095184"
PID = "1385494113167740928"
SLUG = "paper-butterfly-bookmark-set"
TITLE = "Paper Butterfly Bookmark Set"
CATEGORY = "book-accessories"
DESCRIPTION = (
    "Fourteen paper bookmarks with butterflies and botanical prints — each one "
    "slips into a kraft sleeve, ready for novels, journals, or a small gift. "
    "Soft Chinese-aesthetic florals that perch on the page like a garden edge."
)

# Clean product / lifestyle (no size charts)
HERO = "https://cf.cjdropshipping.com/1619162300493.jpg"  # butterflies on book edge

LIFESTYLE = [
    HERO,
    # Full set fanned with kraft sleeves
    "https://cf.cjdropshipping.com/1619162300483.jpg",
    # Grid of sleeves + designs
    "https://cf.cjdropshipping.com/1619162300494.jpg",
    # Close trio — poppy, morning glory, tulip
    "https://cf.cjdropshipping.com/1619162300783.jpg",
    # Lotus + green butterfly with pen / name card
    "https://cf.cjdropshipping.com/1619162300488.jpg",
]

VARIANTS = [
    {
        "vid": "1385521914558156800",
        "sku": "CJJT109518401AZ",
        "name": "14-Pack",
        "cost": 0.99,
        "image": "https://cf.cjdropshipping.com/1619162300783.jpg",
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
        f"${min(prices):.2f}",
        "category",
        product.category,
        "spu",
        SPU,
    )
    db.close()


if __name__ == "__main__":
    main()
