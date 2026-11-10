"""Price the draft "Reading Figure Tulip Night Light" and keep only the 1-piece and 2-piece options.

  python scripts/set_tulip_reader_prices.py          # prints the plan, changes nothing
  python scripts/set_tulip_reader_prices.py --apply  # checks CJ stock and US freight, then updates the draft

Never creates orders or payments and never changes whether the product is active: the listing stays
exactly as visible (or hidden) as it was. Aborts without writing if CJ has no stock for a kept
option, has no US route, or the margin after payment fees and US freight falls under MIN_NET_USD.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PID = "1698953982191874048"
SLUG = "reading-figure-tulip-night-light-resin-bookshelf-sculpture"
# vid -> (price, keep, sort_order)
PLAN = {
    "1698953982217039872": (19.99, True, 0),   # Tulip nightlight-1PCS
    "1699031799399198720": (34.99, True, 1),   # Tulip nightlight-2PCS
    "1699031799428558848": (None, False, 2),   # 4PCS: bulk pack, off
    "1699031799453724672": (None, False, 3),   # 8PCS: bulk pack, off
}
MIN_NET_USD = 3.00


def net_profit(price: float, cost: float, freight: float, cfg: dict) -> float:
    """What is left of one sale in the US, where the store pays the freight."""
    return price - (price * cfg["PAYPAL_PCT"] + cfg["PAYPAL_FIXED"]) - cost - cfg["OPS_FIXED"] - freight


def apply_prices(db, freights: dict[str, float], cfg: dict) -> dict:
    from models import Product

    product = db.query(Product).filter(Product.slug == SLUG).first()
    if product is None or product.supplier != "cj" or product.cj_pid != PID:
        raise ValueError("The draft for this CJ product was not found")
    by_vid = {v.cj_vid: v for v in product.variants}
    if set(PLAN) - set(by_vid):
        raise ValueError("The draft does not have the four expected options")
    report = {}
    for vid, (price, keep, order) in PLAN.items():
        variant = by_vid[vid]
        if keep:
            net = net_profit(price, variant.cost_usd, freights[vid], cfg)
            if net < MIN_NET_USD:
                raise ValueError(f"Margin too low for {variant.name}: {net:.2f} USD after fees and freight")
            report[variant.name] = {"price": price, "cost": variant.cost_usd, "freight": freights[vid], "net": round(net, 2)}
            variant.price_usd = price
        variant.active = keep
        variant.sort_order = order
    first = by_vid["1698953982217039872"]
    product.price_usd = first.price_usd
    product.cost_usd = first.cost_usd
    return report


async def check_supplier() -> dict[str, float]:
    from services import cj

    freights: dict[str, float] = {}
    for vid, (price, keep, _order) in PLAN.items():
        if not keep:
            continue
        await asyncio.sleep(1.3)
        stock = await cj._request("GET", "/product/stock/queryByVid", params={"vid": vid})
        if sum(int(x.get("totalInventoryNum") or 0) for x in stock if x.get("countryCode") == "CN") <= 0:
            raise ValueError("CJ reports no China stock for a kept option")
        await asyncio.sleep(1.3)
        options = await cj.freight_calculate(start_country="CN", end_country="US",
                                             products=[{"vid": vid, "quantity": 1}], zip_code="10001")
        fees = [float(o.get("totalPostageFee", o.get("logisticPrice")))
                for o in options if o.get("totalPostageFee", o.get("logisticPrice")) is not None]
        if not fees:
            raise ValueError("No US shipping route for a kept option")
        freights[vid] = min(fees)
    return freights


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        print(json.dumps({"slug": SLUG, "plan": {v: {"price": p, "keep": k} for v, (p, k, _o) in PLAN.items()}}))
        return 0
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from database import SessionLocal, init_db
    from services import pricing

    freights = await check_supplier()
    init_db()
    with SessionLocal() as db:
        report = apply_prices(db, freights, pricing.pricing_config())
        db.commit()
    print("Updated the draft prices and kept the 1-piece and 2-piece options:", json.dumps(report, ensure_ascii=False))
    print("Verified China stock and US freight. No order, sample order or payment created; active flag untouched.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001
        print(re.sub(r"https?://\S+", "[URL omitted]", str(exc)), file=sys.stderr)
        raise SystemExit(1)
