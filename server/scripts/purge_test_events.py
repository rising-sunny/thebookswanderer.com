#!/usr/bin/env python3
"""Remove test and crawler visits from the live-traffic table.

Matches:
  * sessions started by our own tests (session id "claudetest…");
  * the Meta link-check burst of 2026-10-11 01:10–01:14 UTC (Prineville,
    Forest City, Boardman), recorded before the Meta filter existed;
  * anything from San Francisco since 2026-10-09 — the test environment's
    egress — is listed for review only and deleted with --include-sf.

  python scripts/purge_test_events.py                 # list only
  python scripts/purge_test_events.py --apply         # delete the first two groups
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from sqlalchemy import and_, or_  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import LiveEvent  # noqa: E402

TEST = LiveEvent.session_id.like("claudete%")
META_BURST = and_(
    LiveEvent.ts >= datetime(2026, 10, 11, 1, 10),
    LiveEvent.ts < datetime(2026, 10, 11, 1, 14),
    LiveEvent.city.in_(["Prineville", "Forest City", "Boardman"]),
)
SF = and_(LiveEvent.ts >= datetime(2026, 10, 9), LiveEvent.city == "San Francisco")


def show(title: str, rows: list[LiveEvent]) -> None:
    by = defaultdict(list)
    for r in rows:
        by[r.session_id].append(r)
    print(f"\n{title}: {len(rows)} events in {len(by)} sessions")
    for sid, evs in by.items():
        first = min(e.ts for e in evs)
        e = evs[0]
        print(f"  {first:%Y-%m-%d %H:%M} {sid[:14]:14} {len(evs):3} ev  {e.city or '-'}, {e.country or '-'}  "
              f"src={e.source or e.referrer_domain or 'direct'}  {(e.path or '')[:60]}")


def main() -> int:
    apply = "--apply" in sys.argv
    include_sf = "--include-sf" in sys.argv
    db = SessionLocal()
    sure = db.query(LiveEvent).filter(or_(TEST, META_BURST)).order_by(LiveEvent.ts).all()
    sf = db.query(LiveEvent).filter(SF, ~TEST).order_by(LiveEvent.ts).all()
    show("Test + Meta crawler (deleted with --apply)", sure)
    show("San Francisco since 2026-10-09 (review; deleted only with --include-sf)", sf)
    if not apply:
        print("\nlist only; pass --apply to delete")
        return 0
    doomed = sure + (sf if include_sf else [])
    for r in doomed:
        db.delete(r)
    db.commit()
    print(f"\ndeleted {len(doomed)} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
