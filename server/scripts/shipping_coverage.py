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
  python scripts/shipping_coverage.py --why MX,BR,AR,CL         # why Lulu will not quote these: its own error codes
  python scripts/shipping_coverage.py --why-printify letters-from-the-library --countries US,CA,GB,DE,AU
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


async def why(countries) -> int:
    """Ask Lulu directly, for the first active Lulu book, why a country does not quote. Prints only error code/path/message."""
    import re
    from services import lulu
    db = SessionLocal()
    product = next((p for p in db.query(Product).filter(Product.active.is_(True), Product.supplier == "lulu").order_by(Product.id).all()
                    if any(v.active for v in (p.variants or []))), None)
    if not product:
        print("no active Lulu book with a variant"); return 1
    variant = next(v for v in product.variants if v.active)
    lines = [shipping.lulu_line(product, variant, 1)]
    print(f"probe with {product.slug}\n")

    def short(exc):
        payload = getattr(exc, "payload", None)
        found = []
        def walk(x):
            if isinstance(x, dict):
                if "code" in x and ("path" in x or "message" in x):
                    found.append(f"{x.get('code')}:{x.get('path','')}:{str(x.get('message',''))[:70]}")
                for v in x.values(): walk(v)
            elif isinstance(x, list):
                for v in x: walk(v)
        walk(payload)
        text = "; ".join(found) or re.sub(r"https?://\S+", "[url]", str(payload)[:200])
        return f"{str(exc).split(':')[0]} -> {text}"

    for cc in countries:
        s, city, state, zipc = SAMPLE[cc]
        base = {"name": "Rate estimate", "street1": s, "city": city, "postcode": zipc, "country_code": cc, "phone_number": PHONE}
        print(f"== {cc}")
        for label, extra in (("state as typed", {"state_code": state} if state else {}),
                             ("no state", {}),
                             ("with tax id", {**({"state_code": state} if state else {}), "recipient_tax_id": "12345678901"})):
            addr = {**base, **extra}
            try:
                opts = await lulu.request("POST", "/shipping-options/", {"currency": "USD", "line_items": lines, "shipping_address": addr})
                levels = ",".join(sorted({o.get("level") for o in (opts or []) if o.get("level")})) or "none"
                print(f"  shipping-options [{label}]: ok, levels {levels}")
            except lulu.LuluError as exc:
                print(f"  shipping-options [{label}]: {short(exc)}")
            try:
                await lulu.request("POST", "/print-job-cost-calculations/", {"line_items": lines, "shipping_address": addr, "shipping_option": "MAIL"})
                print(f"  cost calculation [{label}]: ok")
            except lulu.LuluError as exc:
                print(f"  cost calculation [{label}]: {short(exc)}")
            await asyncio.sleep(0.4)
    db.close()
    return 0


async def why_printify(slug, countries) -> int:
    """Ask Printify directly why one product will not quote for a country. Prints only its error text, trimmed."""
    import re
    from services import printify
    db = SessionLocal()
    p = db.query(Product).filter(Product.slug == slug, Product.supplier == "printify").first()
    v = next((v for v in (p.variants if p else []) if v.active), None)
    if not p or not v:
        print("no active Printify product with that slug and a variant"); return 1
    lines = [{"product_id": p.printify_product_id, "variant_id": int(v.printify_variant_id), "quantity": 1}]
    print(f"probe with {p.slug} (variant {v.name})\n")
    for cc in countries:
        a = address(cc)
        addr = {"country": cc, "region": a["state"] if cc == "US" else a["state"], "zip": a["postcode"], "city": a["city"], "address1": a["street1"]}
        addr = {k: val for k, val in addr.items() if val}
        try:
            cost = await printify.shipping_cost(lines, cc, addr)
            print(f"{cc}: ok, standard {cost:.2f}")
        except printify.PrintifyError as exc:
            detail = re.sub(r"https?://\S+", "[url]", str(getattr(exc, "payload", ""))[:260])
            print(f"{cc}: {str(exc)[:90]} | {detail}")
        await asyncio.sleep(0.4)
    db.close()
    return 0


async def main(args) -> int:
    if args.why_printify:
        codes = [c.strip().upper() for c in (args.countries or "US,CA,GB,DE,AU,MX").split(",") if c.strip()]
        bad = [c for c in codes if c not in SAMPLE]
        if bad:
            print("no sample address for:", ", ".join(bad)); return 2
        return await why_printify(args.why_printify, codes)
    if args.why:
        codes = [c.strip().upper() for c in args.why.split(",") if c.strip()]
        bad = [c for c in codes if c not in SAMPLE]
        if bad:
            print("no sample address for:", ", ".join(bad)); return 2
        return await why(codes)
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
    ap.add_argument("--supplier"); ap.add_argument("--slug"); ap.add_argument("--countries"); ap.add_argument("--limit", type=int); ap.add_argument("--why"); ap.add_argument("--why-printify", dest="why_printify")
    raise SystemExit(asyncio.run(main(ap.parse_args())))
