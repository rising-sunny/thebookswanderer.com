"""Import the Christmas 2026 gift edit — eight CJ products, curated by hand.

Variants are a hand-picked subset (Halloween and joke-sign styles left out),
images are the clean shots without text overlays, and the shipping allowance
is folded into every price before the launch pin fires (same basis as
import_cj_product.py / reprice_all_in.py).

  python scripts/import_christmas_gifts.py --dry-run   # quote prices, touch nothing
  python scripts/import_christmas_gifts.py             # write to the DB
  python scripts/import_christmas_gifts.py --slug book-lovers-advent-calendar

Skip the Pinterest launch pins with PINTEREST_LAUNCH_PIN_ENABLED=0.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import pricing as pricing_service

_spec = importlib.util.spec_from_file_location(
    "import_cj_product", Path(__file__).with_name("import_cj_product.py")
)
_icp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_icp)

OSS = "https://oss-cf.cjdropshipping.com/product"
CF = "https://cf.cjdropshipping.com"

PRODUCTS: list[dict] = [
    {
        "slug": "book-lovers-advent-calendar",
        "title": "The Book Lover's Advent Calendar",
        "category": "decor",
        "pid": "1729390559942422528",
        "description": (
            "Twenty-five numbered paper pockets for the first twenty-five days of "
            "December, each one a small bookish surprise — bookmarks, paper "
            "ornaments, little cards. Opens out to about 54 cm wide, so it hangs on "
            "a wall or stands on a shelf beside the books it celebrates."
        ),
        "images": [
            f"{OSS}/2023/11/28/06/ccec3f6d-9ee7-40f3-b64b-c009b3f0f6f0.jpg",
            f"{OSS}/2023/11/28/06/9e72fc4d-2e53-4216-b553-5188c066493e.jpg",
            f"{OSS}/2023/11/28/06/e0447618-9864-4033-a7dc-4fd92ff9447b.jpg",
            f"{OSS}/2023/11/28/06/161fdd18-909b-46a6-b6fd-d1230112ce69.jpg",
        ],
        "variants": [
            ("1729390560349270016", "CJYD190828202BY", "Calendar", 5.47, 0),
        ],
    },
    {
        "slug": "twilight-library-book-nook-kit",
        "title": "Twilight Library Book Nook Kit",
        "category": "decor",
        "pid": "2603240308031611100",
        "description": (
            "A wooden kit that builds into a tiny lamp-lit library — fireplace, "
            "grandfather clock, shelves of miniature books — and slides between "
            "real ones on the shelf. 194 pieces, two or three unhurried hours to "
            "assemble, a touch switch for the warm light (batteries not included). "
            "About 10.5 × 12 × 17.5 cm finished."
        ),
        "images": [
            f"{OSS}/2026/03/24/03/7b9685ae-2397-4aaf-b21b-cc3172de3292_trans.jpeg",
            f"{OSS}/2026/03/24/03/2dbfe867-0052-4084-b464-b8af07260fb9_trans.jpeg",
            f"{OSS}/2026/03/24/03/508b5490-966e-47b3-80a6-94b1582a7413_trans.jpeg",
            f"{OSS}/2026/03/24/03/f1604f14-861f-4281-9b05-703b14e1e386_trans.jpeg",
        ],
        "variants": [
            ("2603240308031611500", "CJYZ280136101AZ", "Kit", 9.62, 0),
        ],
    },
    {
        "slug": "baker-street-book-nook-kit",
        "title": "Baker Street Book Nook Kit",
        "category": "decor",
        "pid": "2083126031012237314",
        "from_country": "US",
        "description": (
            "A London street in miniature for the shelf — lamplit shopfronts, a "
            "phone box, a red underground train that slides out on its rail. "
            "295 wooden pieces, three to five hours of building, three LED lights "
            "that switch on by touch. Ships from our US warehouse, United States "
            "addresses only."
        ),
        "images": [
            f"{CF}/17854560/04be4f4c-060c-4076-96fb-c9b0581eefdc.jpg",
            f"{CF}/17854560/99a9a17c-58a9-416c-828e-8038f5a07a41.jpg",
            f"{CF}/17854560/5d235926-cbad-485b-8d7e-b011c4f4651d.jpg",
            f"{CF}/17854560/60c79fae-5185-4448-bdc3-9618e75f2cce.jpg",
        ],
        "variants": [
            ("2083126031171620866", "CJYZ30260030001", "Kit", 32.49, 0),
        ],
    },
    {
        "slug": "bookshelf-lantern-light",
        "title": "Bookshelf Lantern Light",
        "category": "decor",
        "pid": "2607210336371614200",
        "description": (
            "A small black iron arm with a lantern hanging from it, like a street "
            "lamp for the shelf. The bracket version slips under a row of books "
            "and leans out over the spines; the stand version sits on a desk or "
            "nightstand. Battery-powered warm glow."
        ),
        "images": [
            f"{OSS}/2026/07/21/03/f3279678-05a6-42e0-8da0-67162fa948fc.jpg",
            f"{OSS}/2026/07/22/11/d46ce013-9593-4a34-a47a-1dafc1d28a3f_water.jpeg",
            f"{OSS}/2026/07/21/03/75230db2-d904-4492-aeca-a68b38856051.jpg",
            f"{OSS}/2026/07/21/03/42c1af44-28d8-4bc1-b1b5-807c8533c04e.jpg",
        ],
        "variants": [
            ("2607221149281623300", "CJYD299588411KP", "Shelf bracket · Lantern A", 2.90, 1),
            ("2607220606501631300", "CJYD299588407GT", "Shelf bracket · Lantern B", 2.90, None),
            ("2607210336371615000", "CJYD299588401AZ", "Desk stand · Lantern A", 2.90, 2),
            ("2607210336371616200", "CJYD299588403CX", "Desk stand · Lantern B", 2.90, 0),
            ("2607210336371616900", "CJYD299588404DW", "Desk stand · Lantern C", 2.90, 3),
        ],
        "variant_images": {
            "2607220606501631300": f"{OSS}/2026/07/22/06/8961b1d2-74f2-416a-88ce-51c0e54d3677_water.jpeg",
        },
    },
    {
        "slug": "book-tree-christmas-ornament",
        "title": "Book Tree Christmas Ornament",
        "category": "decor",
        "pid": "1713123777032228864",
        "description": (
            "A Christmas tree made of stacked books, printed on a flat 8 cm acrylic "
            "ornament with a ribbon loop. Eight designs — pick one for your own "
            "tree, or tuck one into a gift as the tag."
        ),
        "images": [
            f"{CF}/quick/product/8c7b6202-8be8-4e64-b3d5-47610f5b927d.jpg",
            f"{CF}/quick/product/22e92a50-4145-4e0c-86cc-4a58c8f2e01d.jpg",
            f"{CF}/quick/product/8a11f624-51dd-4ffd-b532-96e2bbaf197c.jpg",
            f"{CF}/quick/product/442d70c7-5dce-4401-9c5e-f44ddc7d4960.jpg",
        ],
        "variants": [
            ("1713123777107726336", "CJYS187103301AZ", "Book tree · gold star", 0.92, None),
            ("1713123777233555456", "CJYS187103303CX", "Red book tree", 0.92, None),
            ("1713123777296470016", "CJYS187103304DW", "Snowy book tree", 0.92, None),
            ("1713123777170640896", "CJYS187103302BY", "Book tree · Santa hat", 0.92, None),
            ("1713123777355190272", "CJYS187103305EV", "Open-book stack", 0.92, None),
            ("1713123777422299136", "CJYS187103306FU", "Little bookshelf", 0.92, None),
            ("1713123777485213696", "CJYS187103307GT", "Heart bookshelf", 0.92, None),
            ("1713123777548128256", "CJYS187103308HS", "Merry Bookmas disc", 0.92, None),
        ],
    },
    {
        "slug": "heart-bookshelf-ornament",
        "title": "Heart Bookshelf Ornament",
        "category": "decor",
        "pid": "1580888177852821504",
        "description": (
            "A heart-shaped bookcase, shelves full, on a flat 7 × 8 cm acrylic "
            "ornament. Light enough for the thinnest branch; nice on a gift bag "
            "too, where it outlives the wrapping paper."
        ),
        "images": [
            f"{CF}/24002457-7869-408a-91b7-e0fc744e4b71.jpg",
            f"{CF}/b24e5aa3-3c5e-4c9c-afa2-2c64610ae2c9.jpg",
            f"{CF}/578dd3da-7726-48ca-ab55-34b885a4575d.jpg",
            f"{CF}/b962eee3-2331-4b61-92b9-3655ff5fc85b.jpg",
        ],
        "variants": [
            ("1580888177924124672", "CJDZ158743301AZ", "Ornament", 0.80, 0),
        ],
    },
    {
        "slug": "reading-log-bookmarks",
        "title": "Reading Log Bookmarks",
        "category": "book-accessories",
        "pid": "2407080140231606700",
        "description": (
            "Library-card bookmarks with ruled lines for title, dates and a "
            "star rating, or a book-stack tracker to colour in as you finish "
            "each one. Coated card, 3.25 × 7.75 in. A quiet stocking filler for "
            "the reader who keeps count."
        ),
        "images": [
            f"{CF}/quick/product/2c8edeb2-77cd-4b94-9943-439278afbedd.jpg",
            f"{CF}/quick/product/c96d3a5b-4a90-4d91-a1c8-d1ad1e79826a.jpg",
            f"{CF}/quick/product/0ebbfb56-34b5-4dd0-8b1f-5c9890a0d5e4.jpg",
            f"{CF}/quick/product/be40d834-6291-4047-9e74-d8c283c87916.jpg",
        ],
        "variants": [
            ("2407080140231607400", "CJYD207807803CX", "Reading log · set of 3", 1.78, 0),
            ("2407080140231608200", "CJYD207807807GT", "Book tracker · set of 3", 1.78, 2),
        ],
    },
    {
        "slug": "christmas-magnetic-bookmarks",
        "title": "Christmas Magnetic Bookmarks",
        "category": "book-accessories",
        "pid": "1718568023679836160",
        "description": (
            "Two magnetic page markers on a card, folded over the page so they "
            "never slide out. Four wintry designs — gingerbread, snowman, Santa "
            "and a rabbit with fireworks. Small enough to post in a card."
        ),
        "images": [
            f"{OSS}/2023/10/29/09/1ede2d1b-f494-470e-a1b7-44d23d88c487.jpg",
            f"{CF}/quick/product/b01d2f49-ed1b-4922-b02b-7f70a1994355.jpg",
        ],
        "variants": [
            ("1718568023767916544", "CJYD188286301AZ", "Gingerbread", 0.75, None),
            ("1718568023839219712", "CJYD188286302BY", "Snowman", 0.75, None),
            ("1718568023977631744", "CJYD188286304DW", "Santa", 0.75, None),
            ("1718568023906328576", "CJYD188286303CX", "Fireworks rabbit", 0.75, None),
        ],
        "variant_images": {
            "1718568023767916544": f"{CF}/f18cabeb-fee0-4323-b98d-b88cd88b4c74_trans.jpeg",
            "1718568023839219712": f"{CF}/c89b35ab-8762-42c9-ab5c-6dfabb83f6a5_trans.jpeg",
            "1718568023977631744": f"{CF}/61c9be83-375d-4d05-9a6a-5c42847557ed_trans.jpeg",
            "1718568023906328576": f"{CF}/75cf15e2-da35-45dd-b9f7-72a3eb99592c_trans.jpeg",
        },
    },
]

# Ornament variant thumbs: one clean shot per design, in VARIANTS order.
_ORN = [
    "8c7b6202-8be8-4e64-b3d5-47610f5b927d", "fdb169a1-7566-4463-bea3-7599a4d0d59e",
    "22e92a50-4145-4e0c-86cc-4a58c8f2e01d", "c9d0b8d6-398a-4d63-bd6b-14233966d25e",
    "442d70c7-5dce-4401-9c5e-f44ddc7d4960", "8a11f624-51dd-4ffd-b532-96e2bbaf197c",
    "f9eef290-13b5-4932-9eb9-745281cb35bb", "de30d7ed-2472-4c2d-ae23-df335cd75f20",
]
PRODUCTS[4]["variant_images"] = {
    v[0]: f"{CF}/quick/product/{_ORN[i]}.jpg" for i, v in enumerate(PRODUCTS[4]["variants"])
}


def _variant_image(spec: dict, vid: str, img_idx: int | None) -> str:
    if vid in spec.get("variant_images", {}):
        return spec["variant_images"][vid]
    return spec["images"][img_idx or 0]


def quote(spec: dict) -> tuple[float, list[float]]:
    """(allowance, per-variant all-in prices)."""
    origin = spec.get("from_country", "CN")
    allowance = _icp._ship_allowance(spec["variants"][0][0], from_country=origin)
    prices = [
        _icp._round99(pricing_service.retail_from_cost(cost) + allowance)
        for _vid, _sku, _name, cost, _img in spec["variants"]
    ]
    return allowance, prices


def write(spec: dict, prices: list[float]) -> None:
    from database import SessionLocal, init_db
    from models import Product, ProductVariant

    init_db()
    db = SessionLocal()
    product = db.query(Product).filter(Product.slug == spec["slug"]).first()
    if not product:
        product = (
            db.query(Product)
            .filter(Product.cj_pid == spec["pid"], Product.active.is_(True))
            .first()
        )
    if not product:
        product = Product(slug=spec["slug"])
        db.add(product)
    else:
        product.slug = spec["slug"]

    vid, sku, _name, cost, img_idx = spec["variants"][0]
    product.title = spec["title"]
    product.description = spec["description"]
    product.image_url = spec["images"][0]
    product.gallery_json = json.dumps(spec["images"])
    product.details_html = ""
    product.category = spec["category"]
    product.cj_pid = spec["pid"]
    product.cj_vid = vid
    product.cj_sku = sku
    product.cost_usd = cost
    product.price_usd = min(prices)
    product.from_country = spec.get("from_country", "CN")
    product.video_url = ""
    product.video_poster = ""
    product.active = True
    db.flush()

    for old in list(product.variants or []):
        db.delete(old)
    db.flush()

    for i, (v_vid, v_sku, v_name, v_cost, v_img) in enumerate(spec["variants"]):
        db.add(
            ProductVariant(
                product_id=product.id,
                name=v_name,
                cj_vid=v_vid,
                cj_sku=v_sku,
                image_url=_variant_image(spec, v_vid, v_img),
                cost_usd=v_cost,
                price_usd=prices[i],
                sort_order=i,
                active=True,
            )
        )
    db.commit()
    db.refresh(product)
    print(f"  OK product {product.id} {product.slug} variants {len(product.active_variants())}")

    try:
        import asyncio

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

    for spec in PRODUCTS:
        if args.slug and spec["slug"] not in args.slug:
            continue
        allowance, prices = quote(spec)
        spread = f"${min(prices):.2f}" + (
            f"–${max(prices):.2f}" if max(prices) != min(prices) else ""
        )
        print(f"{spec['slug']:<32} allowance ${allowance:5.2f}  price {spread}")
        if not args.dry_run:
            write(spec, prices)


if __name__ == "__main__":
    main()
