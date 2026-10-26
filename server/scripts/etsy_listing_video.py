#!/usr/bin/env python3
"""Upload a product video to its Etsy listing (one per listing; Etsy plays 5-15 s, no sound).

  python scripts/etsy_listing_video.py hyperboloid-sculpture

The listing and file come from scripts/slant3d_products.json (etsy_listing_id, video_url).
Skips the upload when the listing already has a video, so a rerun never adds a second one.
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
from services import etsy, slant3d  # noqa: E402


async def main() -> int:
    data = slant3d.product_spec(sys.argv[1])
    listing, shop = data.get("etsy_listing_id"), (os.getenv("ETSY_SHOP_ID") or "").strip()
    path = ROOT.parent / data.get("video_url", "").lstrip("/")
    if not listing or not shop or not path.is_file():
        print("listing, ETSY_SHOP_ID or video file missing")
        return 1
    async with httpx.AsyncClient(timeout=120) as client:
        headers = {"x-api-key": etsy.api_key(), "Authorization": "Bearer " + await etsy.access_token(client)}
        base = f"{etsy.BASE}/application/shops/{shop}/listings/{listing}/videos"
        have = await client.get(base, headers=headers)
        if have.status_code == 200 and have.json().get("count"):
            print(f"listing {listing} already has a video")
            return 0
        with path.open("rb") as fh:
            response = await client.post(base, headers=headers, data={"name": path.name},
                                         files={"video": (path.name, fh, "video/mp4")})
    print(f"upload to listing {listing}: HTTP {response.status_code}")
    return 0 if response.status_code in (200, 201) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
