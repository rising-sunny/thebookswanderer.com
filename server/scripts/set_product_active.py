#!/usr/bin/env python3
"""Hide or restore a product in the shop.

Its page then 301s to its collection, and the sitemap, daily reel and
Pinterest jobs skip it.

  python scripts/set_product_active.py led-reading-book-light --off
  python scripts/set_product_active.py led-reading-book-light --on
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal, init_db  # noqa: E402
from models import Product  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    slugs = [a for a in args if not a.startswith("--")]
    if not slugs or ("--off" in args) == ("--on" in args):
        print(__doc__)
        return 2
    active = "--on" in args
    init_db()
    db = SessionLocal()
    for slug in slugs:
        p = db.query(Product).filter(Product.slug == slug).first()
        if not p:
            print(f"{slug}: not found")
            continue
        print(f"{slug}: active {p.active} -> {active}")
        p.active = active
    db.commit()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
