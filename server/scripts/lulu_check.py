#!/usr/bin/env python3
"""Check the Lulu API keys and quote print + shipping costs. Creates no orders.

  python scripts/lulu_check.py                 # Reading Passport formats, 40 pages
  python scripts/lulu_check.py 0600X0900BWSTDPB060UW444MXX 120
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import lulu  # noqa: E402

# trim · colour · quality · binding · paper · ppi · finish (see Lulu's pod package docs)
PACKAGES = {
    "pocket 4.25x6.87 colour, saddle stitch": "0425X0687FCSTDSS080CW444GXX",
    "pocket 4.25x6.87 colour, paperback": "0425X0687FCSTDPB080CW444GXX",
    "A5 colour, saddle stitch": "0583X0827FCSTDSS080CW444GXX",
    "A5 colour, coil": "0583X0827FCSTDCO080CW444GXX",
    "A5 b/w, saddle stitch": "0583X0827BWSTDSS060UW444MXX",
}
ADDRESSES = {
    "US": {"name": "Test", "street1": "101 Independence Ave SE", "city": "Washington",
           "state_code": "DC", "postcode": "20540", "country_code": "US", "phone_number": "+12025550100"},
    "GB": {"name": "Test", "street1": "96 Euston Rd", "city": "London",
           "postcode": "NW1 2DB", "country_code": "GB", "phone_number": "+442075550100"},
    "CL": {"name": "Test", "street1": "Av. Libertador Bernardo O'Higgins 651", "city": "Santiago",
           "postcode": "8320000", "country_code": "CL", "phone_number": "+56225550100"},
}


async def main() -> int:
    print(f"env={lulu.base()} configured={lulu.configured()}")
    if not lulu.configured():
        return 1
    packages = {"custom": sys.argv[1]} if len(sys.argv) > 1 else PACKAGES
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    for label, pkg in packages.items():
        print(f"\n{label}  [{pkg}]  {pages} pages")
        for cc, addr in ADDRESSES.items():
            try:
                c = await lulu.cost(pkg, pages, 1, addr)
            except lulu.LuluError as e:
                print(f"  {cc}: {e} {str(e.payload)[:200]}")
                if "auth" in str(e):
                    return 1
                continue
            item = (c.get("line_item_costs") or [{}])[0]
            ship = c.get("shipping_cost") or {}
            print(f"  {cc}: print {item.get('total_cost_excl_tax')}  ship {ship.get('total_cost_excl_tax')}  "
                  f"total {c.get('total_cost_incl_tax')} {c.get('currency')} (incl. tax)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
