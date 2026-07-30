"""
Consolidate the 6 separate Washi Sticker Book products into ONE product
with selectable variants. Run on the VPS:

  cd /var/www/thebookswanderer.com/server
  .venv/bin/python scripts/consolidate_washi_variants.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from database import SessionLocal, init_db  # noqa: E402
from models import Product, ProductVariant  # noqa: E402

PID = "2409160535121624500"
SLUG = "washi-sticker-book"
TITLE = "Washi Sticker Book"
DESC = (
    "Retro Japanese-style washi sticker book for journals and planners. "
    "About 50 sheets per book — choose your design below."
)
CATEGORY = "Journaling"
PRICE = 8.99


def main() -> None:
    init_db()
    db = SessionLocal()

    old = (
        db.query(Product)
        .filter(Product.cj_pid == PID)
        .order_by(Product.id.asc())
        .all()
    )
    print("found", len(old), "products for pid", PID)

    # Collect variant data from old products
    variants_data = []
    gallery = []
    details_html = ""
    for p in old:
        # extract design name from "Washi Sticker Book — X"
        name = p.title
        if "—" in name:
            name = name.split("—", 1)[1].strip()
        elif "-" in name and "Washi" in name:
            name = name.split("-", 1)[-1].strip()
        variants_data.append(
            {
                "name": name or p.cj_sku or f"Option {p.id}",
                "cj_vid": p.cj_vid,
                "cj_sku": p.cj_sku,
                "image_url": p.image_url,
                "cost_usd": p.cost_usd,
                "price_usd": p.price_usd or PRICE,
            }
        )
        if p.image_url and p.image_url not in gallery:
            gallery.append(p.image_url)
        if p.details_html and not details_html:
            details_html = p.details_html
        try:
            for u in json.loads(p.gallery_json or "[]"):
                if u and u not in gallery:
                    gallery.append(u)
        except json.JSONDecodeError:
            pass

    # Deactivate all old rows
    for p in old:
        p.active = False
        # free slug for reuse if needed
        if not p.slug.startswith("archived-"):
            p.slug = f"archived-{p.slug}"[:120]

    # Create parent (or reactivate existing consolidated)
    parent = db.query(Product).filter(Product.slug == SLUG).first()
    if not parent:
        parent = Product(slug=SLUG)
        db.add(parent)

    parent.title = TITLE
    parent.description = DESC
    parent.category = CATEGORY
    parent.cj_pid = PID
    parent.price_usd = PRICE
    parent.cost_usd = variants_data[0]["cost_usd"] if variants_data else 0.51
    parent.image_url = (variants_data[0]["image_url"] if variants_data else "") or ""
    parent.gallery_json = json.dumps(gallery[:16])
    parent.details_html = details_html or ""
    parent.from_country = "CN"
    parent.active = True
    if variants_data:
        parent.cj_vid = variants_data[0]["cj_vid"]
        parent.cj_sku = variants_data[0]["cj_sku"]

    db.flush()

    # Clear existing variants on parent
    for v in list(parent.variants or []):
        db.delete(v)
    db.flush()

    for i, vd in enumerate(variants_data):
        db.add(
            ProductVariant(
                product_id=parent.id,
                name=vd["name"],
                cj_vid=vd["cj_vid"],
                cj_sku=vd["cj_sku"],
                image_url=vd["image_url"],
                cost_usd=vd["cost_usd"],
                price_usd=vd["price_usd"] or PRICE,
                sort_order=i,
                active=True,
            )
        )

    db.commit()
    db.refresh(parent)
    print(
        "parent id",
        parent.id,
        "slug",
        parent.slug,
        "variants",
        len(parent.active_variants()),
    )
    for v in parent.active_variants():
        print(" -", v.id, v.name, v.cj_vid)
    db.close()


if __name__ == "__main__":
    main()
