#!/usr/bin/env python3
"""Publish the fresh pins listed in pin_campaign.json (images in assets/pins/).

Boards named in the JSON are created when missing; pins already published
are recorded in data/pin_campaign_done.json and never posted twice.

  python scripts/pin_campaign.py            # dry run
  python scripts/pin_campaign.py --apply    # create boards and pins
  python scripts/pin_campaign.py --apply --limit 3   # spread pins over days
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import pinterest as pin  # noqa: E402

SPEC = Path(__file__).with_name("pin_campaign.json")
DONE = ROOT / "data" / "pin_campaign_done.json"
IMAGE_BASE = "https://thebookswanderer.com/assets/pins/"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    done = json.loads(DONE.read_text()) if DONE.exists() else {}
    todo = [p for p in spec["pins"] if p["key"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} pin(s) to post, {len(done)} already done")
    if not todo:
        return 0

    boards = {}
    existing = {b["name"].strip().lower(): b["id"] for b in (await pin.list_boards()).get("items", [])}
    for key, b in spec["boards"].items():
        if b.get("id"):
            boards[key] = b["id"]
        elif b["name"].lower() in existing:
            boards[key] = existing[b["name"].lower()]
        elif args.apply and any(p["board"] == key for p in todo):
            boards[key] = (await pin.create_board(name=b["name"], description=b["description"]))["id"]
            print(f"  created board {b['name']} → {boards[key]}")
        else:
            boards[key] = f"(new) {b['name']}"

    for p in todo:
        print(f"  {p['key']} → {boards[p['board']]}: {p['title']}")
        if not args.apply:
            continue
        try:
            res = await pin.create_pin(board_id=boards[p["board"]], title=p["title"], description=p["description"],
                                       link=p["link"], image_url=IMAGE_BASE + p["image"], alt_text=p.get("alt", ""))
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED {getattr(exc, 'detail', exc)}")
            continue
        done[p["key"]] = res.get("id")
        DONE.parent.mkdir(parents=True, exist_ok=True)
        DONE.write_text(json.dumps(done, indent=1))
        print(f"    pinned {res.get('id')}")
        await asyncio.sleep(3)
    if not args.apply:
        print("dry run; pass --apply to publish")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
