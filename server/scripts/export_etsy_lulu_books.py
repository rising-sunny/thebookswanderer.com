#!/usr/bin/env python3
"""Write the store's Lulu books that are on Etsy as extra books for the Etsy → Lulu bridge.

The bridge (Etsy_mathrelaxing/lulu_books/fulfillment.py) polls paid Etsy receipts
and sends mapped books to Lulu. Each entry here carries signed print-file links,
so the output file must stay on the VPS (it goes in the bridge's gitignored output/).

  python scripts/export_etsy_lulu_books.py /opt/etsy_lulu_fulfill/lulu_books/output/tbw_books.json
  python scripts/export_etsy_lulu_books.py -      # print to stdout
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import Product  # noqa: E402
from services import digital, lulu  # noqa: E402
from urls import PUBLIC_BASE  # noqa: E402


def books() -> tuple[dict, list[str]]:
    out, skipped = {}, []
    with SessionLocal() as db:
        rows = db.query(Product).filter(Product.supplier == lulu.SUPPLIER, Product.active == 1).all()
        for p in rows:
            variant = p.default_variant()
            interior = digital.file_for(p, variant)
            cover = (variant.print_cover if variant else "") or ""
            if not p.etsy_listing_id:
                skipped.append(f"{p.id} {p.slug}: not on Etsy")
                continue
            if not (p.lulu_package and digital.file_path(interior) and digital.file_path(cover)):
                skipped.append(f"{p.id} {p.slug}: package or print files missing")
                continue
            out[p.etsy_listing_id] = {
                "slug": p.slug,
                "title": p.title[:80],
                "pod_package_id": p.lulu_package,
                "interior_url": lulu.file_url(PUBLIC_BASE, interior),
                "cover_url": lulu.file_url(PUBLIC_BASE, cover),
            }
    return out, skipped


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data, skipped = books()
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if sys.argv[1] == "-":
        sys.stdout.write(text)
    else:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")
        print(f"{len(data)} book(s) written to {sys.argv[1]}")
    for line in skipped:
        print("skipped:", line, file=sys.stderr)


if __name__ == "__main__":
    main()
