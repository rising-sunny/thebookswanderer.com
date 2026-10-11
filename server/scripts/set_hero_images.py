#!/usr/bin/env python3
"""Swap the main photo of products whose CJ hero is a weak shot.

The new hero leaves the gallery and the old one joins it, so no photo is
lost and none shows twice.

  python scripts/set_hero_images.py            # dry run
  python scripts/set_hero_images.py --apply
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
from models import Product  # noqa: E402

HEROES = {
    # The old hero was the cover on its own, which reads as a tote bag.
    "washable-kraft-book-cover": "https://cf.cjdropshipping.com/quick/product/e6796c32-7336-4c3b-8090-c145ddb34002.jpg",
    # The old hero was a dimension diagram.
    "adjustable-reading-stand": "https://oss-cf.cjdropshipping.com/product/2025/03/18/07/1c76ddc5-a9e0-416e-a1c2-a2a7857bf984_trans.jpeg",
}


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    init_db()
    db = SessionLocal()
    for slug, url in HEROES.items():
        p = db.query(Product).filter(Product.slug == slug).first()
        if not p:
            print(f"{slug}: not found")
            continue
        if p.image_url == url:
            print(f"{slug}: already set")
            continue
        gallery = [u for u in json.loads(p.gallery_json or "[]") if u != url]
        if p.image_url and p.image_url not in gallery:
            gallery.append(p.image_url)
        print(f"{slug}: {p.image_url} -> {url} (gallery {len(gallery)})")
        if apply:
            p.image_url = url
            p.gallery_json = json.dumps(gallery)
    if apply:
        db.commit()
        print("applied")
    else:
        print("dry run; pass --apply to save")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
