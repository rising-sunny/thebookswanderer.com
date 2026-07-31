"""Import CJYD2076904 — Magnetic Kindle sleeve (ereader-accessories)."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal, init_db
from models import Product, ProductVariant
from services import pricing as pricing_service

PID = "2407060547311625000"
SLUG = "kindle-magnetic-sleeve"
TITLE = "Kindle Magnetic Sleeve"
CATEGORY = "ereader-accessories"
DESCRIPTION = (
    "A soft suede-feel sleeve with a magnetic flap for Kindle and other e-readers. "
    "Slips in, seals shut, and keeps the screen safe in a bag. Choose color and size "
    "to match your device (6\", 6.8\", 7\", or Kindle Scribe 10.2\")."
)

# Clean in-use / product shots (no marketing headlines, no dimension diagrams)
HERO = "https://cf.cjdropshipping.com/quick/product/1a80e6d0-0ee4-4cb5-aa82-3dc30b318a7d.jpg"

LIFESTYLE = [
    HERO,  # pink open + closed (no overlay)
    # Multi-color lineup — prefer self-hosted crop without title band
    "/assets/products/kindle-sleeve/lineup.jpg",
]

# Color source images (CJ; labels cropped for picker thumbs)
COLOR_SOURCES = {
    "Pink": "https://cf.cjdropshipping.com/quick/product/27bec111-60c4-4c17-95c9-083a6c7918aa.jpg",
    "Light Blue": "https://cf.cjdropshipping.com/quick/product/f333b31e-033b-4444-8ea6-61367e2d423a.jpg",
    "Dark Gray": "https://cf.cjdropshipping.com/quick/product/5b840365-0126-4b71-b80a-e9beced2fb21.jpg",
    "Light Gray": "https://cf.cjdropshipping.com/quick/product/06ef0bc8-abdc-4f5a-9160-78706ac954fb.jpg",
    "Khaki": "https://cf.cjdropshipping.com/quick/product/ee31bbf3-2957-410c-bfed-c03c80eeb914.jpg",
}

LINEUP_SRC = (
    "https://cf.cjdropshipping.com/quick/product/635b0f2f-4acc-4579-b995-26bce4bec815.jpg"
)

SIZES = [
    ("6inch Universal", '6"', 2.70),
    ("6.8inch Universal", '6.8"', 2.70),
    ("7inch Universal", '7"', 2.70),
    ("kindle scribe 10.2inch", 'Scribe 10.2"', 3.51),
]

# Full CJ variant table in stable order: color × size
VARIANTS_META = [
    # Pink
    ("2407060547311625300", "CJYD207690401AZ", "Pink", "6inch Universal"),
    ("2407060547311625800", "CJYD207690403CX", "Pink", "6.8inch Universal"),
    ("2407060547311625600", "CJYD207690402BY", "Pink", "7inch Universal"),
    ("2407060547311626000", "CJYD207690404DW", "Pink", "kindle scribe 10.2inch"),
    # Light Blue
    ("2407060547311626200", "CJYD207690405EV", "Light Blue", "6inch Universal"),
    ("2407060547311626600", "CJYD207690407GT", "Light Blue", "6.8inch Universal"),
    ("2407060547311626400", "CJYD207690406FU", "Light Blue", "7inch Universal"),
    ("2407060547311626800", "CJYD207690408HS", "Light Blue", "kindle scribe 10.2inch"),
    # Dark Gray
    ("2407060547311627000", "CJYD207690409IR", "Dark Gray", "6inch Universal"),
    ("2407060547311627400", "CJYD207690411KP", "Dark Gray", "6.8inch Universal"),
    ("2407060547311627200", "CJYD207690410JQ", "Dark Gray", "7inch Universal"),
    ("2407060547311627600", "CJYD207690412LO", "Dark Gray", "kindle scribe 10.2inch"),
    # Light Gray
    ("2407060547311627800", "CJYD207690413MN", "Light Gray", "6inch Universal"),
    ("2407060547311628200", "CJYD207690415OL", "Light Gray", "6.8inch Universal"),
    ("2407060547311628000", "CJYD207690414NM", "Light Gray", "7inch Universal"),
    ("2407060547311628400", "CJYD207690416PK", "Light Gray", "kindle scribe 10.2inch"),
    # Khaki
    ("2407060547311628600", "CJYD207690417QJ", "Khaki", "6inch Universal"),
    ("2407060547311629000", "CJYD207690419SH", "Khaki", "6.8inch Universal"),
    ("2407060547311628800", "CJYD207690418RI", "Khaki", "7inch Universal"),
    ("2407060547311629200", "CJYD207690420TG", "Khaki", "kindle scribe 10.2inch"),
]

SIZE_COST = {s[0]: s[2] for s in SIZES}
SIZE_LABEL = {s[0]: s[1] for s in SIZES}


def assets_dir() -> Path:
    local = ROOT.parent / "assets" / "products" / "kindle-sleeve"
    if local.parent.exists() or True:
        vps = Path("/var/www/thebookswanderer.com/assets/products/kindle-sleeve")
        if vps.parent.exists():
            return vps
    return local


def crop_assets(out: Path) -> dict[str, str]:
    """Crop color-label badges; crop title band on lineup. Return color→local path."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
    except ImportError:
        print("PIL missing — using remote color URLs")
        return {c: u for c, u in COLOR_SOURCES.items()}

    color_urls: dict[str, str] = {}
    for color, url in COLOR_SOURCES.items():
        slug = color.lower().replace(" ", "-")
        dest = out / f"{slug}.jpg"
        tmp = out / f"_src_{slug}.jpg"
        urllib.request.urlretrieve(url, tmp)
        im = Image.open(tmp).convert("RGB")
        w, h = im.size
        # Label badge sits top-right; crop top ~12% and slight right margin noise
        top = int(h * 0.10)
        im.crop((0, top, w, h)).save(dest, "JPEG", quality=90)
        tmp.unlink(missing_ok=True)
        color_urls[color] = f"/assets/products/kindle-sleeve/{slug}.jpg"
        print("cropped color", dest.name)

    # Lineup: remove "Amazon kindle magnetic liner bag" title
    tmp = out / "_src_lineup.jpg"
    urllib.request.urlretrieve(LINEUP_SRC, tmp)
    im = Image.open(tmp).convert("RGB")
    w, h = im.size
    im.crop((0, int(h * 0.16), w, h)).save(out / "lineup.jpg", "JPEG", quality=90)
    tmp.unlink(missing_ok=True)
    print("cropped lineup")
    return color_urls


def main() -> None:
    color_urls = crop_assets(assets_dir())

    variants = []
    for i, (vid, sku, color, size_key) in enumerate(VARIANTS_META):
        cost = SIZE_COST[size_key]
        label = f"{color} · {SIZE_LABEL[size_key]}"
        variants.append(
            {
                "vid": vid,
                "sku": sku,
                "name": label,
                "cost": cost,
                "image": color_urls.get(color, COLOR_SOURCES[color]),
                "sort": i,
            }
        )

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

    default = variants[0]
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

    prices = []
    for v in variants:
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
                sort_order=v["sort"],
                active=True,
            )
        )
        print(f"  {v['name']}: ${v['cost']:.2f} → ${price:.2f}")

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
    )
    db.close()


if __name__ == "__main__":
    main()
