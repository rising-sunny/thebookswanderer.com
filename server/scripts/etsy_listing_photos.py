#!/usr/bin/env python3
"""Add photos to an Etsy listing from image URLs (Etsy only takes uploaded files, not links).

  python scripts/etsy_listing_photos.py 4608346944 https://.../a.jpg https://.../b.jpg

The photos go after the ones already on the listing, in the order given. Skips the run when
the listing already has at least that many extra photos, so a rerun never adds duplicates.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
from services import etsy  # noqa: E402


async def main() -> int:
    listing, urls = sys.argv[1], sys.argv[2:]
    shop = (os.getenv("ETSY_SHOP_ID") or "").strip()
    if not listing.isdigit() or not urls or not shop:
        print("usage: etsy_listing_photos.py LISTING_ID URL... (and ETSY_SHOP_ID set)")
        return 1
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        headers = {"x-api-key": etsy.api_key(), "Authorization": "Bearer " + await etsy.access_token(client)}
        have = await client.get(f"{etsy.BASE}/application/listings/{listing}/images", headers=headers)
        count = have.json().get("count", 0) if have.status_code == 200 else 0
        if count > len(urls):
            print(f"listing {listing} already has {count} photos")
            return 0
        failed = 0
        for rank, url in enumerate(urls, count + 1):
            image = await client.get(url)
            kind = image.headers.get("content-type", "")
            if image.status_code != 200 or not kind.startswith("image/"):
                print(f"skip {url[:80]}: HTTP {image.status_code} {kind}")
                failed += 1
                continue
            r = await client.post(f"{etsy.BASE}/application/shops/{shop}/listings/{listing}/images",
                                  headers=headers, data={"rank": str(rank)},
                                  files={"image": (f"photo-{rank}.jpg", image.content, kind)})
            print(f"photo {rank} to listing {listing}: HTTP {r.status_code}")
            failed += r.status_code not in (200, 201)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
