"""Import CJYD2069969 — Palace Kitten paper bookmark set (30 pcs)."""
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

SPU = "CJYD2069969"
PID = "2406270638361620300"
SLUG = "palace-kitten-bookmarks"
TITLE = "Palace Kitten Bookmark Set"
CATEGORY = "book-accessories"
DESCRIPTION = (
    "Thirty paper bookmarks of palace cats among plum blossom and red walls — "
    "soft guofeng scenes for novels, journals, and letters. Slip one between the "
    "pages or fan the whole set on the desk; each pack is a small gallery of "
    "kittens in bloom."
)

# Lifestyle / beauty (no marketing text overlays)
HERO = "https://cf.cjdropshipping.com/quick/product/95fa8fc4-9ef7-464a-9480-553bc92b6a70.jpg"

LIFESTYLE = [
    HERO,  # fan layout on desk + glasses
    # Full set grid
    "https://cf.cjdropshipping.com/quick/product/26ccc117-ff1e-42a3-b5b1-c74c63c6ebed.jpg",
    # Journal / candle reading corner
    "https://cf.cjdropshipping.com/quick/product/df519b1c-5a4a-4dc9-b171-e02a5661415f.jpg",
    # Circular fan of all designs
    "https://cf.cjdropshipping.com/quick/product/b1d50db7-77ed-476e-9492-ce03f23bba06.jpg",
    # Hand hold — white cat on branch
    "https://cf.cjdropshipping.com/quick/product/3ff28e75-c3f6-4628-b0cb-82f27ce8de9c.jpg",
    # Hand hold — ginger cat + blossom
    "https://cf.cjdropshipping.com/quick/product/6a479f85-e3af-4551-a724-fef4a12e5145.jpg",
    # Hand hold — snow / plum scene
    "https://cf.cjdropshipping.com/quick/product/1158259c-8ebc-4d47-b81f-4abd16f33a05.jpg",
    # Alternate full grid
    "https://cf.cjdropshipping.com/quick/product/28152f0f-8863-4e8d-a27c-0f5de734c7b6.jpg",
]

VARIANTS = [
    {
        "vid": "2406270638361620600",
        "sku": "CJYD206996901AZ",
        "name": "30-Pack",
        "cost": 0.92,
        "image": (
            "https://cf.cjdropshipping.com/quick/product/"
            "26ccc117-ff1e-42a3-b5b1-c74c63c6ebed.jpg"
        ),
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
