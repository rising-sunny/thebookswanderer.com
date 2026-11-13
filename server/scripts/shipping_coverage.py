#!/usr/bin/env python3
"""Which countries can each physical product really ship to? Quotes only: no orders, no payments, nothing is saved.

Asks the same live quote the checkout uses (services/shipping.quote) for each active physical product's
first variant and a sample address in about 25 countries, and prints one compact block per product:
the countries that quote, the extra delivery cost over the included US shipping, the ones the provider
cannot reach, and the ones that need a fuller address. Provider replies are not printed, only our own
messages. Needs the store's .env on the server.

  python scripts/shipping_coverage.py --supplier lulu            # one provider at a time is gentler
  python scripts/shipping_coverage.py --supplier printify --limit 5
  python scripts/shipping_coverage.py --slug kerstnacht-poster
  python scripts/shipping_coverage.py --countries US,GB,ES,AR,MX,BR
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import Product  # noqa: E402
from services import shipping  # noqa: E402

PHONE = "+15555550123"
# Public landmark addresses, only to let providers resolve a postal route. Nothing is ordered.
SAMPLE = {
    "US": ("101 Independence Ave SE", "Washington", "DC", "20540"),
    "CA": ("100 Queen St W", "Toronto", "ON", "M5H 2N2"),
    "MX": ("Av Juarez 1", "Ciudad de Mexico", "CMX", "06000"),
    "GB": ("96 Euston Rd", "London", "", "NW1 2DB"),
    "IE": ("1 O'Connell St", "Dublin", "", "D01 F5P2"),
    "DE": ("Unter den Linden 1", "Berlin", "", "10117"),
    "FR": ("1 Rue de Rivoli", "Paris", "", "75001"),
    "ES": ("Calle Mayor 1", "Madrid", "Madrid", "28013"),
    "IT": ("Via del Corso 1", "Roma", "RM", "00186"),
    "NL": ("Damrak 1", "Amsterdam", "", "1012 LG"),
    "BE": ("Rue de la Loi 16", "Bruxelles", "", "1000"),
    "PT": ("Praca do Comercio 1", "Lisboa", "", "1100-148"),
    "SE": ("Drottninggatan 1", "Stockholm", "", "111 51"),
    "CH": ("Bundesplatz 3", "Bern", "", "3003"),
    "AT": ("Heldenplatz 1", "Wien", "", "1010"),
    "PL": ("Plac Zamkowy 4", "Warszawa", "", "00-277"),
    "AU": ("1 Macquarie St", "Sydney", "NSW", "2000"),
    "NZ": ("1 The Terrace", "Wellington", "", "6011"),
    "JP": ("1-1 Chiyoda", "Tokyo", "Tokyo", "100-0001"),
    "BR": ("Av Paulista 1000", "Sao Paulo", "SP", "01310-100"),
    "AR": ("Balcarce 50", "Buenos Aires", "Buenos Aires", "C1064"),
    "CL": ("Alameda 651", "Santiago", "RM", "8320000"),
    "CO": ("Carrera 7 No 6-54", "Bogota", "DC", "110111"),
    "ZA": ("1 Parliament St", "Cape Town", "WC", "8001"),
    "IN": ("Rajpath", "New Delhi", "DL", "110001"),
    "SG": ("1 Raffles Place", "Singapore", "", "048616"),
}


def address(cc: str) -> dict:
    s, city, state, zipc = SAMPLE[cc]
    return {"street1": s, "city": city, "state": state, "postcode": zipc, "phone_number": PHONE}


async def one(product, variant, cc):
    try:
        q = await shipping.quote([(product, variant, 1)], cc, address(cc))
        return "ok", float(q.get("shipping_total") or 0.0), ""
    except shipping.QuoteError as exc:
        kind = {"no_route": "none", "address_required": "addr"}.get(exc.reason, "err")
        return kind, 0.0, str(exc)[:90]
    except Exception as exc:  # noqa: BLE001 - never print provider payloads
        return "err", 0.0, type(exc).__name__


async def main(args) -> int:
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()] if args.countries else list(SAMPLE)
    bad = [c for c in countries if c not in SAMPLE]
    if bad:
        print("no sample address for:", ", ".join(bad)); return 2
    db = SessionLocal()
    rows = [p for p in db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all()
            if (p.supplier or "cj") != "digital"
            and (not args.supplier or (p.supplier or "cj") == args.supplier)
            and (not args.slug or p.slug == args.slug)]
    if args.limit:
        rows = rows[: args.limit]
    totals: dict[str, list[int]] = {}
    for p in rows:
        sup = p.supplier or "cj"
        variants = [v for v in (p.variants or []) if v.active]
        v = variants[0] if variants else None
        ok, none, addr, err, first_msg = {}, [], [], [], ""
        for cc in countries:
            kind, cost, msg = await one(p, v, cc)
            if kind == "ok": ok[cc] = cost
            elif kind == "none": none.append(cc)
            elif kind == "addr": addr.append(cc)
            else:
                err.append(cc)
                first_msg = first_msg or msg
            await asyncio.sleep(0.25)
        t = totals.setdefault(sup, [0, 0]); t[0] += len(ok); t[1] += len(countries)
        print(f"\n{p.slug}  [{sup}]  quotes {len(ok)}/{len(countries)}")
        if ok:
            print("  extra over US: " + ", ".join(f"{c} {x:.2f}" for c, x in ok.items()))
        if none: print("  provider cannot reach: " + ", ".join(none))
        if addr: print("  needs a fuller address: " + ", ".join(addr))
        if err: print("  could not quote (error): " + ", ".join(err) + (f"  e.g. {first_msg}" if first_msg else ""))
    print("\nSummary by provider (countries that quote / countries tried, summed over products):")
    for sup, (a, b) in sorted(totals.items()):
        print(f"  {sup}: {a}/{b}")
    db.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--supplier"); ap.add_argument("--slug"); ap.add_argument("--countries"); ap.add_argument("--limit", type=int)
    raise SystemExit(asyncio.run(main(ap.parse_args())))
