#!/usr/bin/env python3
"""Daily Pinterest drip (cron on VPS).

  # one pin (default PINTEREST_PINS_PER_DAY)
  python scripts/pinterest_auto_pin.py

  # dry-run candidates
  python scripts/pinterest_auto_pin.py --dry-run

  # force N pins this run
  python scripts/pinterest_auto_pin.py --limit 2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


async def main() -> int:
    from database import SessionLocal, init_db
    from services import pinterest_jobs as jobs

    ap = argparse.ArgumentParser(description="Pinterest daily auto-pin")
    ap.add_argument("--limit", type=int, default=None, help="Pins this run (default env)")
    ap.add_argument("--dry-run", action="store_true", help="List candidates only")
    args = ap.parse_args()

    if args.dry_run:
        init_db()
        db = SessionLocal()
        try:
            n = args.limit if args.limit is not None else jobs.pins_per_day()
            cands = jobs.select_drip_candidates(db, limit=n)
            print(
                json.dumps(
                    {
                        "enabled": jobs.auto_pin_enabled(),
                        "pins_per_day": jobs.pins_per_day(),
                        "cooldown_days": jobs.repin_cooldown_days(),
                        "candidates": [
                            {
                                "slug": p.slug,
                                "title": p.title,
                                "category": p.category,
                                "board_id": jobs.board_id_for_category(p.category),
                                "last_pin": (
                                    jobs.last_successful_pin_at(db, p.slug).isoformat()
                                    if jobs.last_successful_pin_at(db, p.slug)
                                    else None
                                ),
                            }
                            for p in cands
                        ],
                    },
                    indent=2,
                    default=str,
                )
            )
        finally:
            db.close()
        return 0

    result = await jobs.run_daily_drip(limit=args.limit)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") or result.get("skipped") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
