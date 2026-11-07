#!/usr/bin/env python3
"""Link already-installed print PDFs to a Lulu product's variants. Changes nothing else.

  python scripts/link_print_files.py SLUG INTERIOR.pdf COVER.pdf

Both files must already be in the digital files folder (see services/digital.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import Product  # noqa: E402
from services import digital  # noqa: E402


def main(slug: str, interior: str, cover: str) -> int:
    if not (digital.file_path(interior) and digital.file_path(cover)):
        print("interior or cover missing from the digital files folder")
        return 1
    with SessionLocal() as db:
        p = db.query(Product).filter(Product.slug == slug, Product.supplier == "lulu").first()
        if not p or not p.variants:
            print(f"{slug}: no Lulu product with variants")
            return 1
        for v in p.variants:
            v.digital_file, v.print_cover = interior, cover
        db.commit()
        print(f"{slug}: linked {len(p.variants)} variant(s)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    raise SystemExit(main(*sys.argv[1:]))
