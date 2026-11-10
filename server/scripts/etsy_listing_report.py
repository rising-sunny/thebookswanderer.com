#!/usr/bin/env python3
"""Read-only: every active Etsy listing of the shop, compact, sorted by views. Prints no buyer data.

  python scripts/etsy_listing_report.py

One line per listing: views | favourites | USD | type | id | title. Used to rank listings and find the
ones nobody sees. The Etsy token stays on this server; nothing is written to Etsy.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SHOP = 66586766


def line(listing: dict) -> tuple:
    price = listing.get("price") or {}
    usd = (price.get("amount") or 0) / (price.get("divisor") or 100)
    title = re.sub(r"\s+", " ", str(listing.get("title") or "")).strip()[:75]
    return (int(listing.get("views") or 0), int(listing.get("num_favorers") or 0), round(usd, 2),
            str(listing.get("listing_type") or ""), listing.get("listing_id"), title)


async def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from services import etsy

    rows, total = [], None
    async with httpx.AsyncClient(timeout=60) as client:
        headers = {"x-api-key": etsy.api_key(), "Authorization": "Bearer " + await etsy.access_token(client)}
        offset = 0
        while True:
            r = await client.get(f"{etsy.BASE}/application/shops/{SHOP}/listings",
                                 params={"state": "active", "limit": 100, "offset": offset}, headers=headers)
            if r.status_code == 429:
                await asyncio.sleep(2)
                continue
            r.raise_for_status()
            data = r.json()
            total = data.get("count")
            rows += [line(x) for x in data.get("results", [])]
            offset += 100
            if offset >= (total or 0) or not data.get("results"):
                break
            await asyncio.sleep(0.3)
    rows.sort(key=lambda x: (-x[0], -x[1]))
    zero = [x for x in rows if x[0] == 0]
    print(f"etsy listing report: {len(rows)} active listings read (Etsy says {total}); {len(zero)} with 0 views")
    print("views | favs | usd | type | id | title")
    for v, f, usd, kind, lid, title in rows:
        print(f"{v} | {f} | {usd} | {kind} | {lid} | {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
