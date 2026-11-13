#!/usr/bin/env python3
"""Create the Kerstnacht poster in Printify by copying the annotated Pride and Prejudice poster.

Same blueprint, print provider, sizes and placement; only the artwork, title and description change, and
only the sizes the print files can carry (see SIZES). The product is created in the Printify shop and is NOT
published anywhere; creating it makes no customer order and no payment.

  python scripts/create_printify_poster.py             # dry run: reads the source product, prints the plan
  python scripts/create_printify_poster.py --apply     # uploads the three print files and creates the product

The print files are served from /assets/products/kerstnacht-poster/ on the live site (deploy first).
Needs PRINTIFY_API_TOKEN and PRINTIFY_SHOP_ID in the server's .env. Prints ids and sizes, never keys.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import crosslist, printify  # noqa: E402

SOURCE = "6ae94afb85d0437faf021bbb"          # annotated-pride-and-prejudice-poster (see import_printify_products.py)
BASE = "https://thebookswanderer.com/assets/products/kerstnacht-poster"
FILES = {"2x3": 2 / 3, "3x4": 3 / 4, "4x5": 4 / 5}
# The scan is 2607 px wide and sits upscaled in the file: up to 18 x 24 in stays near 160 dpi of real detail.
SIZES = {(11, 14), (12, 16), (12, 18), (16, 20), (16, 24), (18, 24)}
TITLE = "Christmas Eve (Kerstnacht) Poster, Van Hoytema 1894 Lithograph, Matte Print"
DESCRIPTION = (
    "Two snowy owls, a flight of geese and a star over a frozen holly wood: \"Christmas Eve\" (Kerstnacht), "
    "a lithograph by Theodorus van Hoytema from 1894, in the public domain and reproduced from the "
    "Metropolitan Museum of Art's Open Access collection. Museum-style matte paper on a warm paper tone with a "
    "small caption; frame not included. Printed to order in the US; check your destination for delivery "
    "availability and the total."
)


def size_of(variant: dict) -> tuple[int, int] | None:
    nums = re.findall(r"\d+", (variant.get("title") or "").split(" / ")[0])
    return (int(nums[0]), int(nums[1])) if len(nums) >= 2 else None


def nearest(ratio: float) -> str:
    return min(FILES, key=lambda k: abs(FILES[k] - ratio))


async def main(apply: bool) -> int:
    if not printify.configured():
        print("PRINTIFY_API_TOKEN / PRINTIFY_SHOP_ID not configured")
        return 1
    shop = printify.shop_id()
    src = await printify._request("GET", f"/shops/{shop}/products/{SOURCE}.json")
    print(f"source: blueprint {src['blueprint_id']}, provider {src['print_provider_id']}, {len(src['variants'])} variants")
    keep = []
    for v in src["variants"]:
        s = size_of(v)
        ok = bool(v.get("is_enabled")) and s in SIZES
        keep.append((v["id"], v["title"], ok, v["price"]))
        if ok:
            print(f"  keep {v['title']}  price {v['price'] / 100:.2f}")
    if not any(k[2] for k in keep):
        print("no source variant matches the allowed sizes; nothing to create")
        return 1
    # which of our files fits each print area, from the shape of the source artwork
    plan = []
    for area in src["print_areas"]:
        ids = [i for i in area["variant_ids"] if any(k[0] == i and k[2] for k in keep)]
        img = next((im for ph in area["placeholders"] for im in ph.get("images", [])), None)
        if not ids or not img:
            continue
        ratio = img["width"] / img["height"]
        plan.append((area, ids, nearest(ratio)))
        print(f"  area {len(ids)} kept variants, source art {img['width']}x{img['height']} -> print-{nearest(ratio)}.jpg")
    if not apply:
        print("dry run: nothing created")
        return 0
    uploaded = {}
    for key in sorted({p[2] for p in plan}):
        up = await printify._request("POST", "/uploads/images.json", {"file_name": f"kerstnacht-{key}.jpg", "url": f"{BASE}/print-{key}.jpg"})
        uploaded[key] = up["id"]
        print(f"uploaded print-{key}.jpg -> {up['id']} ({up.get('width')}x{up.get('height')})")
    # twin_payload copies variants and placement; then point each area at its own file
    payload = crosslist.twin_payload(src, title=TITLE, description=DESCRIPTION)
    enabled = {k[0] for k in keep if k[2]}
    for v in payload["variants"]:
        v["is_enabled"] = v["id"] in enabled
    areas = []
    for area, ids, key in plan:
        placeholders = [{"position": ph["position"],
                         "images": [{"id": uploaded[key], **{k: im[k] for k in ("x", "y", "scale", "angle") if k in im}}
                                    for im in ph["images"]]}
                        for ph in area["placeholders"] if ph.get("images")]
        areas.append({"variant_ids": ids, "placeholders": placeholders})
    payload["print_areas"] = areas
    payload["tags"] = ["poster", "christmas", "owl", "holly", "vintage print", "winter"]
    made = await printify._request("POST", f"/shops/{shop}/products.json", payload)
    print(f"created Printify product {made['id']} (not published). Enabled sizes: {len(enabled)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main("--apply" in sys.argv)))
    except Exception as exc:  # provider messages can carry signed URLs
        print(re.sub(r"https?://\S+", "[url]", str(exc)), file=sys.stderr)
        raise SystemExit(1)
