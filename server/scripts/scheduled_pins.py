#!/usr/bin/env python3
"""Publish owner-approved Pinterest pins at their scheduled time (cron, every 10 min).

  python scripts/scheduled_pins.py [--dry-run]

Reads scripts/scheduled_pins.json (exact texts approved by the owner by merging the PR that adds them).
Each pin goes out once: a ledger in /var/lib/tbw-once/scheduled-pins/<id> is written after success.
Pins more than 36 h late are skipped. Independent of PINTEREST_AUTO_PIN_ENABLED (that flag only
governs the automatic drip). Prints ids and pin ids only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
from services import pinterest  # noqa: E402

LEDGER = Path("/var/lib/tbw-once/scheduled-pins")
IMAGES = "https://thebookswanderer.com/assets/pins/"
MAX_LATE = timedelta(hours=36)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    pins = json.loads((Path(__file__).parent / "scheduled_pins.json").read_text(encoding="utf-8"))
    LEDGER.mkdir(parents=True, exist_ok=True)
    now, failed = datetime.now(timezone.utc), 0
    for p in pins:
        done = LEDGER / p["id"]
        due = datetime.fromisoformat(p["publish_at"].replace("Z", "+00:00"))
        if done.exists() or due > now:
            continue
        if now - due > MAX_LATE:
            print(f"{p['id']}: skipped (more than 36 h late)")
            continue
        if args.dry_run:
            print(f"{p['id']}: due, would publish")
            continue
        try:
            r = await pinterest.create_pin(board_id=p["board_id"], title=p["title"], description=p["description"],
                                           link=p["link"], image_url=IMAGES + p["image"], alt_text=p.get("alt_text", ""))
        except Exception as exc:  # retried on the next run
            print(f"{p['id']}: failed ({type(exc).__name__})")
            failed += 1
            continue
        done.write_text(str(r.get("id", "")))
        print(f"{p['id']}: published pin {r.get('id')}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
