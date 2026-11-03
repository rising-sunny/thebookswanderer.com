"""Local copies of Printify mockup images for crawlers.

images-api.printify.com disallows /mockup/ in its robots.txt, so Google Merchant Center cannot
fetch those images and disapproves the products. scripts/mirror_printify_images.py saves each
mockup used by an active product under /assets/products/printify-mirror/, and the product feed
points to that copy when it exists.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

HOST = "https://images-api.printify.com/"
SITE_ROOT = Path(__file__).resolve().parents[2]
DIR = SITE_ROOT / "assets" / "products" / "printify-mirror"
PUBLIC = "/assets/products/printify-mirror/"


def needs_mirror(url: str) -> bool:
    return bool(url) and url.startswith(HOST)


def filename(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:24] + ".jpg"


def local(url: str) -> str:
    """The on-site copy of a Printify image if it exists, else the original URL."""
    if needs_mirror(url) and (DIR / filename(url)).is_file():
        return PUBLIC + filename(url)
    return url
