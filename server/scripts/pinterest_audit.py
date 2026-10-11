#!/usr/bin/env python3
"""Read-only audit of the shop's Pinterest pins.

For every pin on every board it checks that the link goes to this site, to a
/products/<slug> page of an active product, that the page answers 200, and
that the pin title still matches the product. It also cross-checks the
pinterest_pins table (pins the site created) against what Pinterest has.
Nothing is created, edited or deleted.

  python scripts/pinterest_audit.py
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import PinterestPin, Product  # noqa: E402
from services import pinterest as pin  # noqa: E402
from services import pinterest_jobs as jobs  # noqa: E402


async def all_pins(board_id: str) -> list[dict]:
    pins, bookmark = [], None
    while True:
        params = {"page_size": 100}
        if bookmark:
            params["bookmark"] = bookmark
        page = await pin.api_request("GET", f"/boards/{board_id}/pins", params=params)
        pins += page.get("items") or []
        bookmark = page.get("bookmark")
        if not bookmark:
            return pins
        await asyncio.sleep(0.5)


async def main() -> int:
    if not pin.is_configured():
        print("Pinterest app not configured (PINTEREST_CLIENT_ID / SECRET)")
        return 1
    print("token:", pin.token_health())
    print(f"auto pins enabled={jobs.auto_pin_enabled()} per_day={jobs.pins_per_day()} "
          f"launch={jobs.launch_pin_enabled()} cooldown_days={jobs.repin_cooldown_days()}")

    db = SessionLocal()
    products = {p.slug: p for p in db.query(Product).all()}
    records = db.query(PinterestPin).all()
    site_host = urlparse(pin.public_base()).hostname

    boards = (await pin.list_boards()).get("items") or []
    found: dict[str, dict] = {}
    for b in boards:
        items = await all_pins(b["id"])
        print(f"board {b['id']} {b.get('name')!r}: {len(items)} pins")
        for it in items:
            it["_board"] = b.get("name")
            found[str(it["id"])] = it

    problems: list[str] = []
    per_slug: Counter = Counter()
    page_status: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        for pid, it in found.items():
            link = (it.get("link") or "").strip()
            title = (it.get("title") or "").strip()
            where = f"pin {pid} [{it['_board']}] {title[:40]!r}"
            if not link:
                problems.append(f"{where}: no link")
                continue
            u = urlparse(link)
            if u.hostname not in (site_host, f"www.{site_host}"):
                problems.append(f"{where}: links off-site -> {link}")
                continue
            parts = [p for p in u.path.split("/") if p]
            if len(parts) != 2 or parts[0] != "products":
                problems.append(f"{where}: not a product link -> {u.path}")
                continue
            slug = parts[1]
            per_slug[slug] += 1
            prod = products.get(slug)
            if not prod:
                problems.append(f"{where}: unknown product slug {slug}")
                continue
            if not prod.active:
                problems.append(f"{where}: product {slug} is inactive")
            if title and title.lower() != (prod.title or "").lower()[:100]:
                problems.append(f"{where}: title differs from product {prod.title!r}")
            if "utm_source" not in parse_qs(u.query):
                problems.append(f"{where}: link has no utm_source")
            if slug not in page_status:
                try:
                    page_status[slug] = (await http.get(link)).status_code
                except httpx.HTTPError:
                    page_status[slug] = 0
            if page_status[slug] != 200:
                problems.append(f"{where}: page answers {page_status[slug]} -> {link}")

    recorded = {r.pin_id for r in records if r.pin_id and r.status == "active"}
    missing = sorted(recorded - set(found))
    manual = sorted(set(found) - recorded)
    failed = [r for r in records if r.status == "failed"]

    print(f"\n{len(found)} pins on Pinterest, {len(recorded)} recorded by the site, "
          f"{len(failed)} failed attempts in the log")
    print(f"products with pins: {len(per_slug)} of {sum(1 for p in products.values() if p.active)} active")
    never = sorted(s for s, p in products.items() if p.active and s not in per_slug)
    if never:
        print("active products without any pin:", ", ".join(never))
    if missing:
        print(f"recorded but no longer on Pinterest ({len(missing)}):", ", ".join(missing[:20]))
    if manual:
        print(f"on Pinterest but not created by the site ({len(manual)}):", ", ".join(manual[:20]))
    for r in failed[-10:]:
        print(f"failed {r.created_at:%Y-%m-%d} {r.product_slug} {r.kind}: {r.error[:120]}")
    print(f"\nproblems ({len(problems)}):")
    for p in problems:
        print(" -", p)
    if not problems:
        print(" none: every pin links to a live product page")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
