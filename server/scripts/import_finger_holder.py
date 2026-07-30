"""Import CJJT1393689 — Wooden Finger Book Holder (only video SPCJJT13936890002)."""
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

SPU = "CJJT1393689"
PID = "1478538723816771584"
SLUG = "wooden-finger-book-holder"
TITLE = "Wooden Finger Book Holder"
CATEGORY = "Reading Accessories"
DESCRIPTION = (
    "Slip this solid-wood finger buckle over the page and free a hand for coffee, "
    "notes, or turning the next chapter. Smooth beech or black walnut — a small "
    "reading tool that feels as good as it works."
)

# Self-hosted video (SPCJJT13936890002 only)
VIDEO_URL = "/assets/products/finger-book-holder/demo.mp4"
VIDEO_POSTER = (
    "https://cf.cjdropshipping.com/965f5b74-0096-4f56-bbd9-3855bc5e230f.jpg"
)

HERO = "https://cf.cjdropshipping.com/965f5b74-0096-4f56-bbd9-3855bc5e230f.jpg"

# Ambient lifestyle only (not variant cutouts / size diagrams)
LIFESTYLE = [
    HERO,
    # In use — one-handed reading
    "https://cf.cjdropshipping.com/23abd78d-7087-4418-b856-98b2856a3336.jpg",
    # Close-up on open book
    "https://cf.cjdropshipping.com/7d3cf219-eb31-41da-9e21-0e5e2587f9a5.jpg",
    # Beech on books with berries
    "https://cf.cjdropshipping.com/35244111-50ee-40fb-8dc2-8aaa6acfa905.jpg",
    # Walnut + berries on kraft books
    "https://cf.cjdropshipping.com/17138304/2404230901290323100.jpg",
    # Beech on open pages, soft lights
    "https://cf.cjdropshipping.com/17138304/2404230901290327600.jpg",
    # Walnut wood-grain detail
    "https://cf.cjdropshipping.com/17138304/2404230901300322600.jpg",
]

# Friendly option names (keep pack clear for pricing)
VARIANTS = [
    {
        "vid": "1478538723938406401",
        "sku": "CJJT139368902BY",
        "name": "Beech",
        "cost": 0.80,
        "image": "https://cf.cjdropshipping.com/141ad5b0-0e15-4d66-9590-6ba140a0a60c.png",
    },
    {
        "vid": "1478538723942600705",
        "sku": "CJJT139368904DW",
        "name": "Black Walnut",
        "cost": 1.55,
        "image": "https://cf.cjdropshipping.com/ee6c95b0-8d33-4f81-adaa-ca70c9c70a1b.png",
    },
    {
        "vid": "2603270537111602400",
        "sku": "CJJT139368905EV",
        "name": "Black Walnut · 3-Pack",
        "cost": 4.65,
        "image": "https://oss-cf.cjdropshipping.com/product/2026/03/27/05/8284298a-9ce8-45a6-b07a-5034d45a8060.jpg",
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
    product.video_url = VIDEO_URL
    product.video_poster = VIDEO_POSTER
    product.active = True
    db.flush()

    for v in list(product.variants or []):
        db.delete(v)
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
        print(f"  variant {v['name']}: cost ${v['cost']:.2f} → ${price:.2f}")

    db.commit()
    db.refresh(product)
    print(
        "OK",
        product.id,
        product.slug,
        "variants",
        len(product.active_variants()),
        "video",
        product.video_url,
        "price",
        product.price_usd,
    )
    db.close()


if __name__ == "__main__":
    main()
