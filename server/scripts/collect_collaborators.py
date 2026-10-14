#!/usr/bin/env python3
"""Daily professional-contact research. Never sends mail.

python scripts/collect_collaborators.py --limit 20
python scripts/collect_collaborators.py --dry-run
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from services.collaborators import ResearchError, collect_site
from services import collaborators_store as store
import httpx


def run(limit=20, force=False, dry_run=False) -> dict:
    store.init_store()
    lock_path = store.data_dir() / "collector.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "already_running"}
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat(timespec="seconds")
        with store.connect() as db:
            query = "SELECT * FROM sources WHERE active=1"
            values = []
            if not force:
                query += " AND (checked_at IS NULL OR checked_at < ?)"
                values.append(cutoff)
            query += " ORDER BY checked_at IS NOT NULL, checked_at, id LIMIT ?"
            values.append(max(1, min(20, limit)))
            sources = [dict(r) for r in db.execute(query, values)]
        if dry_run:
            return {"status": "dry_run", "sites_due": len(sources), "sources": [{"id": s["id"], "name": s["name"], "url": s["url"]} for s in sources]}
        with store.connect() as db:
            # A prior process interrupted by a deploy/timeout no longer holds
            # the lock. Keep its audit row with an explicit interrupted state.
            db.execute("UPDATE runs SET status='interrupted',finished_at=? WHERE status='running'", (store.now(),))
            run_id = db.execute("INSERT INTO runs(started_at) VALUES(?)", (store.now(),)).lastrowid
        totals = {"status": "completed", "sites": 0, "found": 0, "added": 0, "errors": 0}
        deadline = time.monotonic() + 25 * 60
        try:
            for source in sources:
                if time.monotonic() > deadline:
                    totals["status"] = "partial"
                    break
                try:
                    items, message = collect_site(source)
                except (ResearchError, httpx.HTTPError, OSError) as exc:
                    items = []
                    message = str(exc) if isinstance(exc, ResearchError) else "Error de red; se volverá a intentar en la próxima revisión."
                    totals["errors"] += 1
                with store.connect() as db:
                    # A source paused during a crawl must not gain new contacts.
                    active = db.execute("SELECT active FROM sources WHERE id=?", (source["id"],)).fetchone()
                    if not active or not active["active"]:
                        continue
                    for item in items:
                        totals["added"] += int(store.save_candidate(db, source["id"], item))
                    db.execute("UPDATE sources SET checked_at=?,last_status=? WHERE id=?", (store.now(), message[:350], source["id"]))
                    totals["sites"] += 1
                    totals["found"] += len(items)
                    db.execute("UPDATE runs SET sites=?,found=?,added=?,errors=? WHERE id=?", (totals["sites"], totals["found"], totals["added"], totals["errors"], run_id))
        except Exception:
            totals["status"] = "failed"
            raise
        finally:
            with store.connect() as db:
                db.execute("UPDATE runs SET finished_at=?,status=? WHERE id=?", (store.now(), totals["status"], run_id))
        return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--force", action="store_true", help="Review sources even if checked today")
    parser.add_argument("--dry-run", action="store_true", help="List due sources; no network or candidate changes")
    args = parser.parse_args()
    # No raw pages, emails or credentials in Actions logs.
    print(json.dumps(run(args.limit, args.force, args.dry_run), ensure_ascii=False))


if __name__ == "__main__":
    main()
