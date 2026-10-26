#!/usr/bin/env python3
"""Create or update a 3D print from scripts/slant3d_products.json. Never orders or charges.

  python scripts/publish_slant3d_products.py hyperboloid-sculpture            # check only
  python scripts/publish_slant3d_products.py hyperboloid-sculpture --publish  # upsert and activate

Publishing needs Slant 3D ready on this server (key, platform, SLANT3D_ORDERS_ENABLED and
SLANT3D_CONTACT_EMAIL), so a buyer can never pay for a print the store cannot order.
Each variant carries its manifest SKU in cj_sku; checkout and Etsy route by that SKU.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
from services import slant3d  # noqa: E402

FIELDS = ["title", "title_es", "description", "description_es", "details_html", "category",
          "image_url", "price_usd", "cost_usd"]


def stage(db, data, *, publish=False):
    from models import Product, ProductVariant
    product = db.query(Product).filter_by(slug=data["slug"]).first()
    if product and product.supplier != slant3d.SUPPLIER:
        raise ValueError("Existing slug belongs to another supplier")
    if product is None:
        product = Product(slug=data["slug"], supplier=slant3d.SUPPLIER)
        db.add(product)
    for field in FIELDS:
        setattr(product, field, data[field])
    product.gallery_json = json.dumps(data["gallery"])
    product.from_country = "US"
    product.cj_pid = product.cj_vid = product.cj_sku = ""
    product.active, product.draft = publish, not publish
    db.flush()
    existing = {v.cj_sku: v for v in product.variants}
    for order, spec in enumerate(data["variants"]):
        variant = existing.pop(spec["sku"], None) or ProductVariant(product_id=product.id, cj_sku=spec["sku"])
        db.add(variant)
        variant.name, variant.image_url, variant.sort_order = spec["name"], spec["image_url"], order
        variant.price_usd, variant.cost_usd, variant.active, variant.cj_vid = data["price_usd"], data["cost_usd"], True, ""
    for leftover in existing.values():
        leftover.active = False
    db.flush()
    return product


def check(data):
    missing = [u for u in [data["image_url"], *data["gallery"], *(v["image_url"] for v in data["variants"])]
               if not (ROOT.parent / u.lstrip("/")).is_file()]
    if missing:
        raise ValueError("Images missing: " + ", ".join(missing))
    for v in data["variants"]:
        slant3d.lines(data["slug"], 1, v["sku"])


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    data = slant3d.product_spec(sys.argv[1])
    check(data)
    publish = "--publish" in sys.argv
    if publish and not (slant3d.ready() and os.getenv("SLANT3D_CONTACT_EMAIL")):
        print("Slant 3D is not ready on this server (key, platform, SLANT3D_ORDERS_ENABLED, SLANT3D_CONTACT_EMAIL); not published")
        return 1
    if not publish:
        print(f"{data['slug']}: {len(data['variants'])} variants, {data['price_usd']} USD, images ok. Use --publish to apply.")
        return 0
    from database import SessionLocal, init_db
    init_db()
    db = SessionLocal()
    product = stage(db, data, publish=True)
    db.commit()
    print(f"published {product.slug} (id {product.id}) with {len(data['variants'])} variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
