#!/usr/bin/env python3
"""Check the Lulu API keys and quote print + shipping costs. Creates no orders.

  python scripts/lulu_check.py                 # Reading Passport formats, 40 pages
  python scripts/lulu_check.py 0600X0900BWSTDPB060UW444MXX 120
  python scripts/lulu_check.py --countries 0583X0827FCSTDPB080CW444GXX 40   # every country, MAIL + GROUND
  python scripts/lulu_check.py --probe       # which hardcover / linen / calendar codes exist, US cost
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
    "pocket 4.25x6.87 colour, saddle stitch, uncoated": "0425X0687FCSTDSS060UW444MXX",
    "pocket 4.25x6.87 b/w, paperback": "0425X0687BWSTDPB060UW444MXX",
    "pocket 4.25x6.87 colour, paperback": "0425X0687FCSTDPB080CW444GXX",
    "A5 colour, saddle stitch, uncoated": "0583X0827FCSTDSS060UW444MXX",
    "A5 colour premium, saddle stitch": "0583X0827FCPRESS080CW444GXX",
    "A5 colour, coil": "0583X0827FCSTDCO080CW444GXX",
    "A5 b/w, saddle stitch": "0583X0827BWSTDSS060UW444MXX",
    "A5 colour, paperback": "0583X0827FCSTDPB080CW444GXX",
}
ADDRESSES = {
    "US": {"name": "Test", "street1": "101 Independence Ave SE", "city": "Washington",
           "state_code": "DC", "postcode": "20540", "country_code": "US", "phone_number": "+12025550100"},
    "GB": {"name": "Test", "street1": "96 Euston Rd", "city": "London",
           "postcode": "NW1 2DB", "country_code": "GB", "phone_number": "+442075550100"},
    "CL": {"name": "Test", "street1": "Alameda 651", "city": "Santiago",
           "postcode": "8320000", "country_code": "CL", "phone_number": "+56225550100"},
}
MORE = {
    "CA": {"street1": "100 Queen St W", "city": "Toronto", "state_code": "ON", "postcode": "M5H 2N2"},
    "AU": {"street1": "1 Macquarie St", "city": "Sydney", "state_code": "NSW", "postcode": "2000"},
    "DE": {"street1": "Unter den Linden 1", "city": "Berlin", "postcode": "10117"},
    "FR": {"street1": "1 Rue de Rivoli", "city": "Paris", "postcode": "75001"},
    "ES": {"street1": "Calle Mayor 1", "city": "Madrid", "postcode": "28013"},
    "IT": {"street1": "Via del Corso 1", "city": "Roma", "postcode": "00186"},
    "NL": {"street1": "Damrak 1", "city": "Amsterdam", "postcode": "1012 LG"},
    "IE": {"street1": "1 O'Connell St", "city": "Dublin", "postcode": "D01 F5P2"},
    "MX": {"street1": "Av Juarez 1", "city": "Ciudad de Mexico", "state_code": "CMX", "postcode": "06000"},
}
for cc, a in MORE.items():
    ADDRESSES[cc] = {"name": "Test", "country_code": cc, "phone_number": "+15555550100", **a}
del ADDRESSES["CL"]  # Lulu needs the recipient's tax id (RUT) for Chile


def probe_candidates() -> list[tuple[str, int]]:
    """Hardcover (casewrap, linen wrap with foil) in A5, and wall calendars.
    Lulu's 27-char code: trim(9) colour(2) quality(3) binding(2) paper(8)
    finish(1) linen(1) foil(1); invalid ones just come back as unknown."""
    out = []
    for q in ("STD", "PRE"):
        for fin in ("G", "M"):
            out.append((f"0583X0827FC{q}CW080CW444{fin}XX", 40))
    for linen in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for foil in ("G",):
            for fin in ("M", "X"):
                out.append((f"0583X0827FCSTDLW080CW444{fin}{linen}{foil}", 40))
    for trim in ("1100X0850", "0850X1100", "1100X0817", "1200X0900"):
        for q in ("PRE", "STD"):
            for paper in ("100CW444", "080CW444"):
                for fin in ("G", "M", "X"):
                    out.append((f"{trim}FC{q}WO{paper}{fin}XX", 28))
    return out


async def probe() -> int:
    us = ADDRESSES["US"]
    found = 0
    for pkg, pages in probe_candidates():
        try:
            c = await lulu.cost(pkg, pages, 1, us)
        except lulu.LuluError as e:
            if "does not exist" not in str(e.payload) and "auth" in str(e):
                print(f"{pkg}: {e}")
                return 1
            if "does not exist" not in str(e.payload):
                print(f"  {pkg} {pages}p: {str(e.payload)[:160]}")
            continue
        found += 1
        item = (c.get("line_item_costs") or [{}])[0]
        ship = c.get("shipping_cost") or {}
        try:
            dim = await lulu.request("POST", "/cover-dimensions/",
                                     {"pod_package_id": pkg, "interior_page_count": pages, "unit": "pt"})
        except lulu.LuluError:
            dim = "?"
        print(f"  OK {pkg} {pages}p: print {item.get('total_cost_excl_tax')} ship {ship.get('total_cost_excl_tax')} "
              f"total US {c.get('total_cost_incl_tax')}  cover {dim}")
    print(f"{found} valid package(s)")
    return 0


async def main() -> int:
    print(f"env={lulu.base()} configured={lulu.configured()}")
    if not lulu.configured():
        return 1
    if "--probe" in sys.argv:
        return await probe()
    argv = [a for a in sys.argv[1:] if a != "--countries"]
    every = "--countries" in sys.argv
    packages = {"custom": argv[0]} if argv else PACKAGES
    pages = int(argv[1]) if len(argv) > 1 else 40
    if every:
        pkg = next(iter(packages.values()))
        try:
            dim = await lulu.request("POST", "/cover-dimensions/",
                                     {"pod_package_id": pkg, "interior_page_count": pages, "unit": "pt"})
            print(f"cover {pkg} {pages}p: {dim}")
        except lulu.LuluError as e:
            print(f"cover dimensions: {e} {str(e.payload)[:200]}")
        for cc, addr in ADDRESSES.items():
            row = []
            for level in ("MAIL", "GROUND"):
                try:
                    c = await lulu.cost(pkg, pages, 1, addr, level)
                    row.append(f"{level} ship {(c.get('shipping_cost') or {}).get('total_cost_excl_tax')} "
                               f"total {c.get('total_cost_incl_tax')}")
                except lulu.LuluError as e:
                    row.append(f"{level} n/a ({str(e.payload)[:80]})")
            print(f"  {cc}: " + " | ".join(row))
        return 0
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
