"""Set ambient / lifestyle images on washi-sticker-book (exclude design thumbs)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from database import SessionLocal, init_db
from models import Product

# Ambient / packaging shots from CJ listing (not the 6 design-strip variants)
LIFESTYLE = [
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/81121324-1d84-4320-8c09-69b87b5b2761.jpg",
    "https://cf.cjdropshipping.com/quick/product/a2695c0e-1ec1-4e55-8838-1d7cf093d58d.jpg",
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/5796a4a5-383a-494a-8a42-0a8cac922c96.jpg",
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/c0428f3c-6c30-42a2-8283-af84c373fc1d_trans.jpeg",
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/e7e3085c-98b7-4cb6-b987-efae8bb4ade9_trans.jpeg",
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/e2dcf197-1b5a-497d-9b9c-a055d97c9449_trans.jpeg",
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/cd7f03aa-bca1-4f3f-9cd1-85c1548f54d5_trans.jpeg",
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/b7ee09fe-f540-48dd-83f4-5b99ab2048f5_trans.jpeg",
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/b1c01142-53ef-4e48-b3a5-0f685d4a2283_trans.jpeg",
    "https://oss-cf.cjdropshipping.com/product/2024/09/16/05/6d8b9de0-90dd-448b-b0d4-7575f6504c01_trans.jpeg",
]


def main() -> None:
    init_db()
    db = SessionLocal()
    p = db.query(Product).filter(Product.slug == "washi-sticker-book").first()
    if not p:
        raise SystemExit("product not found")
    p.gallery_json = json.dumps(LIFESTYLE)
    p.details_html = ""
    db.commit()
    print("lifestyle images", len(LIFESTYLE), "on", p.slug)
    db.close()


if __name__ == "__main__":
    main()
