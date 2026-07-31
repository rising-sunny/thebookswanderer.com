"""Assign canonical category slugs to catalog products."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal, init_db
from models import Product

# slug → category slug
ASSIGNMENTS: dict[str, str] = {
    # Physical book tools & journaling on paper books
    "washi-sticker-book": "book-accessories",
    "heart-book-page-holder": "book-accessories",
    "animal-book-clips": "book-accessories",
    "stained-glass-stickers": "book-accessories",
    "wooden-finger-book-holder": "book-accessories",
    "butterfly-metal-bookmark": "book-accessories",
    "silicone-page-clip-bookmark": "book-accessories",
    # Desk ornament / reading corner piece
    "wooden-reading-tracker": "decor",
    # E-reader
    "kindle-magnetic-sleeve": "ereader-accessories",
}


def main() -> None:
    init_db()
    db = SessionLocal()
    for p in db.query(Product).filter(Product.active.is_(True)).all():
        new_cat = ASSIGNMENTS.get(p.slug)
        if not new_cat:
            print("SKIP (no assignment)", p.slug, "kept", repr(p.category))
            continue
        old = p.category
        p.category = new_cat
        print(f"  {p.slug}: {old!r} → {new_cat}")
    db.commit()
    db.close()
    print("done")


if __name__ == "__main__":
    main()
