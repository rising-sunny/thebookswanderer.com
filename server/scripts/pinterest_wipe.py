#!/usr/bin/env python3
"""Delete the pins of the connected Pinterest account (owner request 2026-11-08: start over).

  python scripts/pinterest_wipe.py            # dry run: counts the first page, deletes nothing
  python scripts/pinterest_wipe.py --apply    # deletes, in one batch bounded by --limit and --budget

It only touches the account whose username is TheBooksWanderer, deletes pins one by one
(DELETE /pins/{id}), and removes the matching rows from pinterest_pins. Pins Pinterest refuses to
delete (for example catalogue-managed ones) are remembered and skipped in later batches. Boards and
the account stay. Always exits 0 so a batch never blocks the release queue; run it again with a new
queue id to continue.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

USERNAME = "TheBooksWanderer"
PAGE = 100


async def wipe(
    request: Callable[..., Awaitable[Any]],
    db: Any,
    *,
    apply: bool,
    limit: int,
    budget: float,
    delay: float,
    refused_file: Path,
    pause: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> dict[str, Any]:
    from models import PinterestPin

    account = await request("GET", "/user_account")
    if account.get("username") != USERNAME:
        return {"aborted": f"connected account is {account.get('username')!r}, not {USERNAME!r}"}
    out: dict[str, Any] = {"pin_count_before": account.get("pin_count"), "deleted": 0, "gone": 0,
                           "refused": 0, "stopped": ""}
    try:
        skip = set(json.loads(refused_file.read_text())) if refused_file.exists() else set()
    except (OSError, ValueError):
        skip = set()
    started = time.monotonic()
    bookmark = None
    seen = 0
    while seen < limit and time.monotonic() - started < budget and not out["stopped"]:
        path = f"/pins?page_size={PAGE}&include_protected_pins=true" + (f"&bookmark={bookmark}" if bookmark else "")
        data = await request("GET", path)
        page_next = data.get("bookmark")
        items = [i for i in (data.get("items") or []) if str(i.get("id")) not in skip]
        if not apply:
            out["first_page_deletable"] = len(items)
            break
        refused_here = False
        for item in items:
            if seen >= limit or time.monotonic() - started >= budget:
                out["stopped"] = out["stopped"] or "batch limit or time budget reached"
                break
            pin_id = str(item.get("id"))
            seen += 1
            status = await _delete(request, pin_id, pause)
            if status in ("ok", "gone"):
                out["deleted" if status == "ok" else "gone"] += 1
                db.query(PinterestPin).filter(PinterestPin.pin_id == pin_id).delete()
            elif status == "rate":
                out["stopped"] = "Pinterest rate limit; continue later with a new queue id"
                break
            else:
                out["refused"] += 1
                refused_here = True
                skip.add(pin_id)
                if out["refused"] >= 25 and out["deleted"] == 0 and out["gone"] == 0:
                    out["stopped"] = "Pinterest refuses to delete pins (check the app's access); stopping"
                    break
            await pause(delay)
        db.commit()
        if out["stopped"]:
            break
        # Deleted pins vanish from the list, so list again from the start; only move on with the
        # bookmark when this page still holds pins that were skipped or refused.
        if not items and page_next:
            bookmark = page_next
        elif refused_here and page_next:
            bookmark = page_next
        elif items and not refused_here:
            bookmark = None
        elif not page_next:
            out["listing_finished"] = True
            break
    try:
        refused_file.parent.mkdir(parents=True, exist_ok=True)
        refused_file.write_text(json.dumps(sorted(skip)))
    except OSError:
        pass
    if apply and out.get("listing_finished") and out["refused"] == 0 and not skip:
        db.query(PinterestPin).delete()  # nothing left on Pinterest: reset the local record too
        db.commit()
        out["local_record_reset"] = True
    return out


async def _delete(request, pin_id: str, pause) -> str:
    for attempt in (1, 2):
        try:
            await request("DELETE", f"/pins/{pin_id}")
            return "ok"
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "status_code", None)
            if code == 404:
                return "gone"
            if code == 429:
                if attempt == 1:
                    await pause(30)
                    continue
                return "rate"
            return "refused"
    return "refused"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--budget", type=float, default=470.0, help="seconds")
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from database import SessionLocal, init_db
    from services import digital, pinterest

    if not pinterest.is_configured():
        print("pinterest wipe: Pinterest is not configured")
        return 0
    init_db()
    db = SessionLocal()
    try:
        result = await wipe(pinterest.api_request, db, apply=args.apply, limit=args.limit, budget=args.budget,
                            delay=args.delay,
                            refused_file=digital.digital_dir() / ".release-private" / "pinterest-wipe-refused.json")
    except Exception as exc:  # noqa: BLE001
        result = {"error": f"{type(exc).__name__}: {str(getattr(exc, 'detail', exc))[:200]}"}
    finally:
        db.close()
    print("pinterest wipe:", json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
