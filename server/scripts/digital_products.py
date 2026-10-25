#!/usr/bin/env python3
"""Create or update the shop's digital and Lulu-printed products from
digital_products.json ("supplier": "lulu" plus "lulu_package" for books).

The JSON (next to this script) holds only public listing data — title,
price, images, variants. The files buyers download are uploaded separately
through /admin/digital/ and never live in this (public) repository.

  python scripts/digital_products.py            # dry run
  python scripts/digital_products.py --apply
  python scripts/digital_products.py --apply some-slug   # only that product
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal, init_db  # noqa: E402
from models import Product, ProductVariant  # noqa: E402
from services import digital  # noqa: E402

SPEC = Path(__file__).with_name("digital_products.json")


def main() -> int:
    apply = "--apply" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    specs = json.loads(SPEC.read_text(encoding="utf-8"))
    init_db()
    db = SessionLocal()
    for spec in specs:
        if only and spec["slug"] not in only:
            continue
        p = db.query(Product).filter(Product.slug == spec["slug"]).first()
        new = p is None
        supplier = spec.get("supplier", digital.SUPPLIER)
        if new:
            p = Product(slug=spec["slug"], supplier=supplier, cj_pid=supplier, from_country="")
            db.add(p)
        elif p.supplier != supplier:
            print(f"{spec['slug']}: exists with supplier {p.supplier}, skipped")
            continue
        p.lulu_package = spec.get("lulu_package", "")
        p.title = spec["title"]
        p.description = spec.get("description", "")
        for key in ("title_es", "description_es", "details_html", "cost_usd"):
            if key in spec:
                setattr(p, key, spec[key])
        p.category = spec.get("category", "")
        p.price_usd = float(spec["price_usd"])
        p.image_url = spec.get("image_url", "")
        p.gallery_json = json.dumps(spec.get("gallery", []))
        p.active = bool(spec.get("active", False))
        db.flush()
        existing = {v.name: v for v in p.variants}
        for i, vs in enumerate(spec.get("variants", [])):
            v = existing.get(vs["name"]) or ProductVariant(product_id=p.id, name=vs["name"])
            v.price_usd = float(vs.get("price_usd", p.price_usd))
            v.image_url = vs.get("image_url", "")
            v.sort_order = i
            v.active = True
            v.cj_vid = f"{supplier}-{p.slug}-{i}"
            db.add(v)
        if supplier == "lulu":
            files_ok = bool(p.variants) and all(
                digital.file_path(v.digital_file) and digital.file_path(v.print_cover)
                for v in p.variants if v.active
            )
        else:
            files_ok = bool(digital.file_path(p.digital_file)) or all(
                digital.file_path(v.digital_file) for v in p.variants if v.active
            ) and bool(p.variants)
        print(f"{'create' if new else 'update'} {p.slug}: ${p.price_usd:.2f} active={p.active} "
              f"variants={len(spec.get('variants', []))} files={'ok' if files_ok else 'MISSING — upload at /admin/digital/'}")
        if p.active and not files_ok:
            print("  ! active without its files: buyers could pay and get nothing. Keeping it hidden.")
            p.active = False
    if apply:
        db.commit()
        print("applied")
    else:
        db.rollback()
        print("dry run; pass --apply to save")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
