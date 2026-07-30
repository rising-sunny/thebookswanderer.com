"""
Reprice all active products/variants from CJ cost using services.pricing.
Run on VPS:
  cd /var/www/thebookswanderer.com/server && .venv/bin/python scripts/reprice_catalog.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from database import SessionLocal, init_db
from models import Product
from services import pricing as pricing_service


def main() -> None:
    init_db()
    db = SessionLocal()
    cfg = pricing_service.pricing_config()
    print("config", cfg)
    for p in db.query(Product).filter(Product.active.is_(True)).all():
        variants = p.active_variants()
        if variants:
            for v in variants:
                old = v.price_usd
                b = pricing_service.breakdown(v.cost_usd)
                v.price_usd = b.price_usd
                print(
                    f"  {p.slug} / {v.name}: cost={v.cost_usd:.2f} "
                    f"{old:.2f} → {b.price_usd:.2f} "
                    f"(net≈{b.net_profit_usd:.2f}, margin={b.margin_on_price:.0%})"
                )
            costs = [v.cost_usd for v in variants]
            prices = [v.price_usd for v in variants]
            p.cost_usd = min(costs)
            p.price_usd = min(prices)
        else:
            old = p.price_usd
            b = pricing_service.breakdown(p.cost_usd)
            p.price_usd = b.price_usd
            print(
                f"{p.slug}: cost={p.cost_usd:.2f} {old:.2f} → {b.price_usd:.2f} "
                f"(net≈{b.net_profit_usd:.2f}, margin={b.margin_on_price:.0%})"
            )
        print(
            f"→ product {p.slug} display price ${p.price_usd:.2f} "
            f"(from cost ${p.cost_usd:.2f})"
        )
    db.commit()
    db.close()
    print("done")


if __name__ == "__main__":
    main()
