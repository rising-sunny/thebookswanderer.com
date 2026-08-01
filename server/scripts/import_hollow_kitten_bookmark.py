"""Import CJJT1191597 — Hollow black kitten plastic bookmark (pack sizes)."""
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

SPU = "CJJT1191597"
PID = "1408385930632499200"
SLUG = "hollow-kitten-bookmark"
TITLE = "Hollow Kitten Bookmark"
CATEGORY = "book-accessories"
DESCRIPTION = (
    "A black hollow-cut kitten that peeks over the page like a tiny page-keeper. "
    "Rigid plastic, light enough to sit in a paperback, bold enough to spot on a "
    "desk stack. Pick a single bookmark or a multi-pack for every open book."
)

# Clean lifestyle only (no pack-count “X2/X5” overlays, no dimension diagrams)
HERO = "https://cf.cjdropshipping.com/5041c5fe-d370-4e79-84ee-05404b89feb7.jpg"

LIFESTYLE = [
    HERO,  # on open journal
    # In-use — open book + hands
    "https://cf.cjdropshipping.com/7878b32f-9f1c-40b3-9322-20baa24d559d.jpg",
    # Studio product beauty
    "https://cf.cjdropshipping.com/0d2ed81a-5519-4da4-88d6-2303751b0172.jpg",
    # Flat silhouette beauty
    "https://oss-cf.cjdropshipping.com/product/2025/12/17/06/"
    "515a078f-2261-4fb3-9ed4-818ce4bf1b8a.jpg",
]

# All pack thumbs use clean single shot (CJ pack images stamp X2/X5/X10)
IMG = HERO

VARIANTS = [
    {
        "vid": "1408385932037591040",
        "sku": "CJJT119159701AZ",
        "name": "Single",
        "cost": 0.44,
        "image": IMG,
    },
    {
        "vid": "1503988542878527488",
        "sku": "CJJT119159702BY",
        "name": "2-Pack",
        "cost": 0.80,
        "image": IMG,
    },
    {
        "vid": "2412240644351627900",
        "sku": "CJJT119159705EV",
        "name": "3-Pack",
        "cost": 1.07,
        "image": IMG,
    },
    {
        "vid": "1503988542878527489",
        "sku": "CJJT119159703CX",
        "name": "5-Pack",
        "cost": 1.95,
        "image": IMG,
    },
    {
        "vid": "1503988542882721792",
        "sku": "CJJT119159704DW",
        "name": "10-Pack",
        "cost": 3.37,
        "image": IMG,
    },
    # Black2-1PC (CJJT119159707GT) omitted: same design family, higher unit cost than Single.
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
