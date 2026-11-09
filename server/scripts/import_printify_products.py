"""List the Printify print-on-demand products on the site (US shipping only).

Reads each product from the Printify shop (variant ids, base cost, mockups),
prices it like the CJ catalogue — margin formula plus the US shipping
allowance folded in — and upserts it with supplier="printify".

  python scripts/import_printify_products.py --dry-run
  python scripts/import_printify_products.py
  python scripts/import_printify_products.py --slug readers-2027-desk-calendar

Needs PRINTIFY_API_TOKEN and PRINTIFY_SHOP_ID in server/.env.
Skip the Pinterest launch pins with PINTEREST_LAUNCH_PIN_ENABLED=0.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import pricing as pricing_service
from services import printify

LOCAL = "/assets/products/printify"

PRODUCTS = [
    {
        "slug": "readers-2027-desk-calendar",
        "printify_id": "6acaf5de8ed76a615a0adea3",
        "title": "Readers — A Desk Calendar for 2027",
        "category": "decor",
        "description": (
            "A desk calendar for 2027 with a print of someone reading for every month: "
            "Dürer's St. Jerome in his study, Whistler's girl by the lamp, Rembrandt, "
            "Fantin-Latour, Menzel, Bellows and others, reproduced from the open-access "
            "collection of the Cleveland Museum of Art, each with a line or two on books "
            "by an old author. Spiral-bound and self-standing, 10 × 5 in on satin paper. "
            "Printed to order in the US; ships to US addresses only."
        ),
        "hero": f"{LOCAL}/readers-2027-cover.jpg",
        "local": [f"{LOCAL}/readers-2027-january.jpg", f"{LOCAL}/readers-2027-june.jpg",
                  f"{LOCAL}/readers-2027-october.jpg"],
        # Printify's back-cover mockup shows the factory's production label
        "skip_mockup_camera": {"100992"},
        # the desk-scene mockup is square and shows the object; the flat
        # cover is 2:1 and floats in the 4:5 product frame
        "hero_mockup_camera": "99193",
        "variant_name": "Desk calendar, 10 × 5 in",
    },
    {
        "slug": "library-ephemera-sticker-sheet",
        "printify_id": "6acaf5e2b55938329c0b2d70",
        "title": "Library Ephemera Sticker Sheet",
        "category": "book-accessories",
        "description": (
            "One sheet of the things you used to find inside a library book: a bookplate "
            "with Dürer's sleeping lion, a date-due slip with crooked stamps, a typed "
            "catalogue card for Pride and Prejudice, three spine labels, a 'Reference only' "
            "stamp and a few more. Kiss-cut glossy vinyl on a 5.8 × 8.3 in sheet, for a "
            "Kindle, a journal or a laptop. Write on the bookplate with a permanent marker; "
            "ballpoint smudges on vinyl. Printed to order in the US; ships to US addresses only."
        ),
        "hero": f"{LOCAL}/library-stickers-sheet.jpg",
        "local": [],
        "skip_mockup_camera": set(),
        "variant_name": "Sticker sheet, 5.8 × 8.3 in",
    },
    {
        "slug": "a-literary-year-2027-wall-calendar",
        "printify_id": "6acd172439bbe64f4f00efcd",
        "title": "A Literary Year — Wall Calendar 2027",
        "category": "decor",
        "description": (
            "Twelve classic book illustrations for 2027, one for every month: Manet's Raven for "
            "Poe, Delacroix's Faust and Hamlet, Doré's Sancho Panza, Rackham's Midsummer Night's "
            "Dream, Kemble's Huckleberry Finn, Blake's Canterbury Pilgrims on the cover and more. "
            "Each page carries a line from the book and the authors born that month — Austen, "
            "Tolkien, Woolf, Twain, Christie. Every image is public domain, reproduced from the "
            "Cleveland Museum of Art and the Library of Congress. Spiral-bound wall calendar, "
            "11 × 8.5 in pages (opens to 11 × 17 in), matte paper, hanging hole. "
            "Printed to order in the US; ships to US addresses only."
        ),
        "hero": f"{LOCAL}/literary-year-2027-cover.jpg",
        "local": [f"{LOCAL}/literary-year-2027-january.jpg", f"{LOCAL}/literary-year-2027-june.jpg",
                  f"{LOCAL}/literary-year-2027-october.jpg"],
        "skip_mockup_camera": set(),
        # the hanging mockup shows the object; the flat cover goes second
        "hero_mockup_camera": "60004",
        "variant_name": "Wall calendar, 11 × 8.5 in",
    },
    {
        "slug": "a-christmas-carol-wall-calendar-2027",
        "printify_id": "6af1d6ad6413c89eeb00a6df",
        "title": "A Christmas Carol — Wall Calendar 2027",
        "category": "decor",
        "description": (
            "Twelve illustrations from A Christmas Carol for 2027: ten by Arthur Rackham (1915) and two by "
            "John Leech (1843), the story's first illustrator, whose plates are also on the front and back "
            "covers. Every month carries a line from Dickens, from Marley's chain in January to \"God bless Us, "
            "Every One!\" in December. The illustrations and the text are public domain, reproduced from scans "
            "of the 1915 and 1843 editions. Spiral-bound wall calendar, 11 × 8.5 in pages (opens to 11 × 17 in), "
            "matte paper, hanging hole. "
            "Printed to order in the US; check your destination for delivery availability and the total."
        ),
        "hero": f"{LOCAL}/christmas-carol-2027/front_cover.jpg",
        "local": [f"{LOCAL}/christmas-carol-2027/january.jpg", f"{LOCAL}/christmas-carol-2027/december.jpg"],
        "skip_mockup_camera": set(),
        # the hanging mockup shows the object; the flat cover goes second
        "hero_mockup_camera": "60004",
        "variant_name": "Wall calendar, 11 × 8.5 in",
    },
    {
        "slug": "wizard-of-oz-jigsaw-puzzle",
        "printify_id": "6acd94f6fd7dc1c56b0b3a44",
        "title": "The Wonderful Wizard of Oz — 252-Piece Jigsaw Puzzle",
        "category": "decor",
        "description": (
            "W. W. Denslow's colour plate from the 1900 first edition of The Wonderful Wizard of Oz: "
            "Dorothy scolding the Cowardly Lion on the yellow brick road while Toto, the Scarecrow and "
            "the Tin Woodman look on. Scanned from the original book, cleaned by hand and set on a cream "
            "border with the line it illustrates. 252 pieces, about 11 × 14 in finished, glossy print on "
            "sturdy chipboard, in a gift box with a reference print. An evening's puzzle for a reader. "
            "Printed to order in the US; ships to US addresses only."
        ),
        "hero": f"{LOCAL}/oz-puzzle-art.jpg",
        "local": [],
        # the back of a puzzle is grey board; leave it out
        "skip_mockup_camera": {"59170"},
        # the box-and-pieces scene sells it best
        "hero_mockup_camera": "101813",
        "variant_name": "252 pieces, vertical",
    },
    {
        "slug": "wizard-of-oz-bookmark-cowardly-lion",
        "printify_id": "6acd94f948c79d41740e6531",
        "title": "Cowardly Lion Metal Bookmark — The Wizard of Oz",
        "category": "book-accessories",
        "description": (
            "Denslow's Cowardly Lion from the 1900 first edition of The Wizard of Oz, printed on a slim "
            "aluminium bookmark with a slot that clips over a single page, so it never falls out. "
            "About 1.5 × 5.25 in. A small gift that lasts as long as the book. "
            "Printed to order in the US; ships to US addresses only."
        ),
        "hero": f"{LOCAL}/oz-bookmark-lion.jpg",
        "local": [],
        "skip_mockup_camera": {"19802"},
        "hero_mockup_camera": "19797",
        "variant_name": "Aluminium bookmark, 1.5 × 5.25 in",
    },
    {
        "slug": "wizard-of-oz-bookmark-tin-woodman",
        "printify_id": "6acd94fbb4b7a98e6a05cbb4",
        "title": "Tin Woodman Metal Bookmark — The Wizard of Oz",
        "category": "book-accessories",
        "description": (
            "Denslow's Tin Woodman from the 1900 first edition of The Wizard of Oz, printed on a slim "
            "aluminium bookmark with a slot that clips over a single page, so it never falls out. "
            "About 1.5 × 5.25 in. A small gift that lasts as long as the book. "
            "Printed to order in the US; ships to US addresses only."
        ),
        "hero": f"{LOCAL}/oz-bookmark-tin-woodman.jpg",
        "local": [],
        "skip_mockup_camera": {"19802"},
        "hero_mockup_camera": "19797",
        "variant_name": "Aluminium bookmark, 1.5 × 5.25 in",
    },
    # several enabled variants: one store option per Printify variant, named by its
    # Printify title ("M / Sand"), with a fixed price per size instead of the formula
    {
        "slug": "annotated-pride-and-prejudice-sweatshirt",
        "printify_id": "6ae8c414e30acf0f5604d7d1",
        "title": "Annotated Pride and Prejudice Sweatshirt",
        "category": "book-accessories",
        "description": (
            "The opening of Pride and Prejudice the way a reader leaves it: the first line "
            "highlighted, a wavy underline, a circled word, and notes in the margin (\"the most "
            "famous first line ever\", \"irony!!\", \"poor guy, no say in it\"). Austen's text is "
            "from 1813; the notes and the layout are ours. Printed straight on the fabric, no patch. "
            "Gildan 18000 heavy blend crewneck, 50% cotton and 50% polyester, unisex fit. "
            "Printed to order in the US; ships to US addresses only."
        ),
        "local": [],
        "skip_mockup_camera": {"98503"},          # back view: nothing printed there
        "hero_mockup_camera": "98502",
        "prices": {"S": 46.99, "M": 46.99, "L": 46.99, "XL": 46.99, "2XL": 49.99},
    },
    {
        "slug": "annotated-pride-and-prejudice-mug",
        "printify_id": "6ae8c4026e342209cf08c478",
        "title": "Annotated Pride and Prejudice Mug, 11 oz",
        "category": "decor",
        "description": (
            "An open copy of Pride and Prejudice wraps round this mug: on one side the first line, "
            "highlighted and underlined, with \"the most famous first line ever\" in the margin; on "
            "the other, Mrs. Bennet's \"have you heard that Netherfield Park is let at last?\" with "
            "its own note. A right-handed and a left-handed reader each get a page facing them. "
            "11 oz white ceramic, dishwasher and microwave safe. "
            "Printed to order in the US; ships to US addresses only."
        ),
        "local": [],
        "skip_mockup_camera": set(),
        "hero_mockup_camera": "10393",
        "variant_name": "White ceramic mug, 11 oz",
        "prices": {"11oz": 24.99},
    },
    {
        "slug": "annotated-pride-and-prejudice-tote",
        "printify_id": "6ae94af4ce06fac797082179",
        "title": "Annotated Pride and Prejudice Tote Bag",
        "category": "book-accessories",
        "description": (
            "The opening of Pride and Prejudice the way a reader leaves it: the first line "
            "highlighted, a wavy underline, a circled word, and notes in the margin (\"the most "
            "famous first line ever\", \"irony!!\", \"poor guy, no say in it\"). Austen's text is "
            "from 1813; the notes and the layout are ours. Printed on one side of a natural cotton "
            "canvas tote, heavy 12 oz fabric, 15 x 16 in with 20 in handles. Spot clean and air dry. "
            "Printed to order in the US; check your destination for delivery availability and the total."
        ),
        # Printify only returns the mockups selected for publishing (front and person-front),
        # so the scenes are listed here; the closeup with the care label is left out on purpose.
        "hero": "https://images-api.printify.com/mockup/6ae94af4ce06fac797082179/101409/109940/annotated-pride-and-prejudice-tote-bag.jpg?camera_label=lifestyle-front",
        "local": [
            "https://images-api.printify.com/mockup/6ae94af4ce06fac797082179/101409/109938/annotated-pride-and-prejudice-tote-bag.jpg?camera_label=person-3-front",
            "https://images-api.printify.com/mockup/6ae94af4ce06fac797082179/101409/94288/annotated-pride-and-prejudice-tote-bag.jpg?camera_label=context-front",
            "https://images-api.printify.com/mockup/6ae94af4ce06fac797082179/101409/109939/annotated-pride-and-prejudice-tote-bag.jpg?camera_label=person-4-front",
            "https://images-api.printify.com/mockup/6ae94af4ce06fac797082179/101409/94290/annotated-pride-and-prejudice-tote-bag.jpg?camera_label=closeup-1",
        ],
        # the back is blank
        "skip_mockup_camera": {"93896", "94287", "109948", "109946", "109949", "94289", "109947"},
        "hero_mockup_camera": None,
        "variant_name": "Natural cotton canvas, 15 x 16 in",
    },
    {
        "slug": "annotated-pride-and-prejudice-poster",
        "printify_id": "6ae94afb85d0437faf021bbb",
        "title": "Annotated Pride and Prejudice Poster, Matte Print",
        "category": "decor",
        "description": (
            "The first page of Pride and Prejudice the way a reader leaves it, with a highlighter and "
            "a pen: the most famous first line in English, the irony underlined, \"property\" circled, "
            "Mrs. Bennet's \"have you heard that Netherfield Park is let at last?\" bracketed, and notes "
            "in the margin. Austen's text is from 1813; the notes and the layout are ours. Museum-style "
            "matte paper, standard frame sizes from 11 x 14 to 30 x 40 in; frame not included. "
            "Printed to order in the US; check your destination for delivery availability and the total."
        ),
        "local": [],
        "skip_mockup_camera": set(),
        "mockup_variant": 43144,                  # one size's scenes (18 x 24) for the gallery
        "hero_mockup_camera": "95153",
        "prices": {"11\u2033 x 14\u2033": 21.99, "12\" x 16\"": 27.99, "12\u2033 x 18\u2033": 27.99,
                   "16\u2033 x 20\u2033": 29.99, "16\u2033 x 24\u2033": 31.99, "18\u2033 x 24\u2033": 31.99,
                   "20\u2033 x 30\u2033": 34.99, "24\u2033 x 36\u2033": 42.99, "30\u2033 x 40\u2033": 74.99},
    },
]


def _round99(v: float) -> float:
    return math.floor(v) + 0.99


async def fetch(spec: dict) -> dict:
    p = await printify._request("GET", f"/shops/{printify.shop_id()}/products/{spec['printify_id']}.json")
    variants = [v for v in p["variants"] if v.get("is_enabled")]
    if len(variants) != 1 and "prices" not in spec:
        raise SystemExit(f"{spec['slug']}: expected one enabled variant, got {len(variants)}")
    v = variants[0]
    mockups = [m["src"] for m in p.get("images", [])
               if not any(f"/{cam}/" in m["src"] for cam in spec["skip_mockup_camera"])
               and ("mockup_variant" not in spec or spec["mockup_variant"] in (m.get("variant_ids") or []))]
    ship = await printify.shipping_cost(
        [{"product_id": spec["printify_id"], "variant_id": v["id"], "quantity": 1}], "US")
    return {"variant_id": v["id"], "cost": v["cost"] / 100, "ship": ship, "mockups": mockups,
            "variants": [{"id": x["id"], "title": x["title"], "cost": x["cost"] / 100} for x in variants],
            "images": [(m["src"], set(m.get("variant_ids") or [])) for m in p.get("images", [])]}


def fixed_price(spec: dict, title: str) -> float:
    size = title.split(" / ")[0].strip()
    if size not in spec["prices"]:
        raise SystemExit(f"{spec['slug']}: no price for size {size!r}")
    return spec["prices"][size]


def price(cost: float, ship: float) -> float:
    markup = float(os.getenv("SHIPPING_MARKUP", "1.15"))
    paypal_pct = float(os.getenv("PAYPAL_FEE_PCT", "0.0349"))
    allowance = ship * markup / (1 - paypal_pct)
    return _round99(pricing_service.retail_from_cost(cost) + allowance)


def write(spec: dict, info: dict, retail: float, pin: bool = True) -> None:
    from database import SessionLocal, init_db
    from models import Product, ProductVariant

    init_db()
    db = SessionLocal()
    product = db.query(Product).filter(Product.slug == spec["slug"]).first()
    if not product:
        product = Product(slug=spec["slug"])
        db.add(product)
    hero = spec.get("hero", "")
    cam = spec.get("hero_mockup_camera")
    scene = next((m for m in info["mockups"] if cam and f"/{cam}/" in m), None)
    if scene:
        hero = scene
    if not hero and info["mockups"]:
        hero = info["mockups"][0]
    gallery = [hero, *([spec["hero"]] if scene and spec.get("hero") else []), *spec["local"],
               *[m for m in info["mockups"] if m != scene]]
    product.title = spec["title"]
    product.description = spec["description"]
    product.image_url = hero
    if "prices" in spec:
        # one front shot per colour first, then the rest; Printify makes one set per colour
        front = [m for m in gallery[1:] if cam and f"/{cam}/" in m]
        gallery = [hero, *front, *[m for m in gallery[1:] if m not in front]][:12]
    product.gallery_json = json.dumps(gallery)
    product.details_html = ""
    product.category = spec["category"]
    product.supplier = "printify"
    product.printify_product_id = spec["printify_id"]
    product.cj_pid = ""
    product.cj_vid = ""
    product.cj_sku = ""
    product.cost_usd = info["cost"]
    product.price_usd = retail
    product.from_country = "US"
    product.video_url = ""
    product.video_poster = ""
    product.active = True
    db.flush()
    for old in list(product.variants or []):
        db.delete(old)
    db.flush()
    if "prices" in spec and len(info["variants"]) > 1:
        sizes = list(spec["prices"])
        order = sorted(info["variants"], key=lambda v: (v["title"].split(" / ")[-1], sizes.index(v["title"].split(" / ")[0])))
        for i, v in enumerate(order):
            # the colour's own front mockup when Printify made one
            img = next((src for src, ids in info["images"] if v["id"] in ids and f"/{cam}/" in src), hero)
            db.add(ProductVariant(
                product_id=product.id, name=v["title"], cj_vid="", cj_sku="",
                printify_variant_id=v["id"], image_url=img,
                cost_usd=v["cost"], price_usd=fixed_price(spec, v["title"]), sort_order=i, active=True,
            ))
    else:
        db.add(ProductVariant(
            product_id=product.id, name=spec["variant_name"], cj_vid="", cj_sku="",
            printify_variant_id=info["variant_id"], image_url=hero,
            cost_usd=info["cost"], price_usd=retail, sort_order=0, active=True,
        ))
    db.commit()
    db.refresh(product)
    print(f"  OK product {product.id} {product.slug}")
    if not pin:
        db.close()
        return
    try:
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
    ap.add_argument("--no-pin", action="store_true", help="skip the Pinterest launch pin")
    args = ap.parse_args()
    if not printify.configured():
        raise SystemExit("PRINTIFY_API_TOKEN / PRINTIFY_SHOP_ID missing in server/.env")
    for spec in PRODUCTS:
        if args.slug and spec["slug"] not in args.slug:
            continue
        info = asyncio.run(fetch(spec))
        retail = (min(fixed_price(spec, v["title"]) for v in info["variants"]) if "prices" in spec
                  else price(info["cost"], info["ship"]))
        print(f"{spec['slug']:34} cost ${info['cost']:.2f}  US ship ${info['ship']:.2f}  "
              f"price ${retail:.2f}  mockups {len(info['mockups'])}")
        if not args.dry_run:
            write(spec, info, retail, pin=not args.no_pin)


if __name__ == "__main__":
    main()
