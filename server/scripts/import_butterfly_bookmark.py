"""Import CJYD2331985 — Butterfly Metal Bookmarks (correct variant image mapping)."""
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

PID = "2503191128181616400"
SLUG = "butterfly-metal-bookmark"
TITLE = "Butterfly Metal Bookmark"
CATEGORY = "Reading Accessories"
DESCRIPTION = (
    "A hollow metal bookmark with painted butterflies and a soft tassel — "
    "slides onto the page without creasing, and looks lovely on a nightstand. "
    "Pick the palette that matches your current chapter."
)

# Hero: all four designs unboxed
HERO = "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/9acb690f-ebc9-40b3-87ac-dda1f70d233e.jpg"

# Ambient / in-use (no spec sheets, no marketing quote collages)
LIFESTYLE = [
    HERO,
    # On open book — reading context
    "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/99a12678-a746-46bc-9d08-628aa3369ad8_trans.jpeg",
    # Purple + blue closeup
    "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/f065a422-67f7-4ae0-b6f2-e37efb52fc10_trans.jpeg",
    # Red + gold detail on lace
    "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/8f5bb35b-f4e0-4294-a215-3e6d7af6be57_trans.jpeg",
    # All four in packaging (gift view)
    "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/8ee8b156-c67e-40ab-b1f7-4106903212be_trans.jpeg",
]

# CJ assigned wrong images for Romantic Dance / Flame Song — corrected by packaging label.
# Prefer self-hosted crops without bottom caption text when available.
ASSETS = "/assets/products/butterfly-bookmark"

VARIANTS = [
    {
        "vid": "2503191128181616600",
        "sku": "CJYD233198501AZ",
        "name": "Romantic Dance",
        "cost": 1.45,
        # CJ wrongly used Flame Song packaging; correct is gold/yellow butterflies
        "image": f"{ASSETS}/romantic-dance.jpg",
        "cj_image_wrong": "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/5f7fbceb-6cea-4469-87df-722d9b4aea6a_trans.jpeg",
        "source": "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/0739185a-15c3-42cb-904d-0a85ba0837f0_trans.jpeg",
    },
    {
        "vid": "2503191128181616800",
        "sku": "CJYD233198502BY",
        "name": "Changting Mountain",
        "cost": 1.45,
        "image": f"{ASSETS}/changting-mountain.jpg",
        "source": "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/779627ff-e5fb-4c43-9c01-5bdea7542703_trans.jpeg",
    },
    {
        "vid": "2503191128181617000",
        "sku": "CJYD233198503CX",
        "name": "Song of Flames",
        "cost": 1.45,
        "image": f"{ASSETS}/song-of-flames.jpg",
        "source": "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/5f7fbceb-6cea-4469-87df-722d9b4aea6a_trans.jpeg",
    },
    {
        "vid": "2503191128181617100",
        "sku": "CJYD233198504DW",
        "name": "Moonlight Encounter",
        "cost": 1.45,
        "image": f"{ASSETS}/moonlight-encounter.jpg",
        "source": "https://oss-cf.cjdropshipping.com/product/2025/03/19/11/792170e8-7999-4f82-a930-fed224b3556b_trans.jpeg",
    },
]


def crop_variant_thumbs(out_dir: Path) -> None:
    """Crop bottom caption band from packaging shots for clean picker thumbs."""
    try:
        from PIL import Image
    except ImportError:
        # Fall back to remote CJ URLs without crop
        print("PIL missing — using full packaging URLs")
        for v in VARIANTS:
            v["image"] = v["source"]
        return

    import urllib.request

    out_dir.mkdir(parents=True, exist_ok=True)
    for v in VARIANTS:
        name = v["image"].rsplit("/", 1)[-1]
        dest = out_dir / name
        tmp = out_dir / f"_src_{name}"
        urllib.request.urlretrieve(v["source"], tmp)
        im = Image.open(tmp).convert("RGB")
        w, h = im.size
        # Caption block is roughly bottom 18–22% on these white-bg cards
        crop_h = int(h * 0.80)
        im.crop((0, 0, w, crop_h)).save(dest, "JPEG", quality=90)
        tmp.unlink(missing_ok=True)
        print("cropped", dest, dest.stat().st_size)


def main() -> None:
    # Crop into public assets when run on VPS (or local with assets path)
    assets_root = ROOT.parent / "assets" / "products" / "butterfly-bookmark"
    # On VPS layout: /var/www/thebookswanderer.com/server + /assets
    if not assets_root.exists():
        assets_root = Path("/var/www/thebookswanderer.com/assets/products/butterfly-bookmark")
    crop_variant_thumbs(assets_root)

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
        print(f"  {v['name']}: cost ${v['cost']:.2f} → ${price:.2f} | {v['image']}")

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
    db.close()


if __name__ == "__main__":
    main()
