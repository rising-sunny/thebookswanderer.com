#!/usr/bin/env python3
"""Explore CJ for products worth adding to the catalogue.

Read-only: searches, prices with the store formula, and flags what is
already imported. Never writes to the DB.

  python scripts/cj_explore.py                       # default reading niche
  python scripts/cj_explore.py --keyword "book lamp" # one keyword
  python scripts/cj_explore.py --max-cost 8 --top 5  # cheaper picks only
  python scripts/cj_explore.py --json                # machine readable
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# CJ allows 1 request/second. Stay just under it.
QPS_DELAY = 1.3

# CJ's keyword search is loose: "holder", "sleeve" and "case" pull in car
# mounts, camisoles and key fobs. Keep only titles that read as book/reading
# gear, and drop the recurring off-niche categories outright.
NICHE_RE = re.compile(
    r"\b(book|books|bookmark|bookmarks|reading|reader|kindle|e-?reader|"
    r"page|pages|novel|literary|library|bookshelf|bookend)\b",
    re.IGNORECASE,
)
OFF_NICHE_RE = re.compile(
    r"\b(car|cars|auto|automobile|vehicle|motorcycle|bicycle|bike|"
    r"phone|cellphone|camisole|shirt|shirts|blouse|bra|dress|"
    r"keychain|key)\b",
    re.IGNORECASE,
)


def is_relevant(title: str) -> bool:
    return bool(NICHE_RE.search(title)) and not OFF_NICHE_RE.search(title)

# Keywords that match the store's niche.
DEFAULT_KEYWORDS = [
    "bookmark",
    "book holder",
    "kindle case",
    "reading light",
    "book stand",
    "page holder",
    "book lamp",
    "book sleeve",
    "reading tracker",
    "book clip",
]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _cost_of(item: dict[str, Any]) -> float:
    """CJ returns either a scalar or a "1.20-3.40" range depending on endpoint."""
    raw = item.get("sellPrice")
    if raw is None:
        raw = item.get("productSellPrice") or item.get("sellPriceRange") or 0
    if isinstance(raw, str) and "-" in raw:
        parts = [p.strip() for p in raw.split("-") if p.strip()]
        if parts:
            return _f(parts[0])
    return _f(raw)


def _items_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    """listV2 nests rows as content[].productList[]; tolerate flatter shapes too."""
    out: list[dict[str, Any]] = []
    for bucket in data.get("content") or []:
        if isinstance(bucket, dict) and isinstance(bucket.get("productList"), list):
            out.extend(x for x in bucket["productList"] if isinstance(x, dict))
        elif isinstance(bucket, dict):
            out.append(bucket)
    if not out and isinstance(data.get("list"), list):
        out = [x for x in data["list"] if isinstance(x, dict)]
    return out


def _category_of(item: dict[str, Any]) -> str:
    for key in ("threeCategoryName", "twoCategoryName", "oneCategoryName", "categoryName"):
        value = (item.get(key) or "").strip() if isinstance(item.get(key), str) else ""
        if value:
            return value
    return ""


async def explore(
    keywords: list[str],
    *,
    size: int,
    max_cost: float,
    top: int,
    sort_by: str = "profit",
    strict: bool = True,
) -> dict[str, Any]:
    from database import SessionLocal, init_db
    from models import Product
    from services import cj
    from services import pricing as pricing_service

    if not cj.is_configured():
        return {"error": "CJ_API_KEY is not configured"}

    init_db()
    db = SessionLocal()
    try:
        owned_pids = {
            (p.cj_pid or "").strip() for p in db.query(Product).all() if p.cj_pid
        }
        owned_titles = {
            (p.title or "").strip().lower() for p in db.query(Product).all()
        }
    finally:
        db.close()

    found: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    off_niche = 0

    for index, kw in enumerate(keywords):
        # CJ enforces 1 request/second; pace ourselves instead of burning
        # keywords on 429s.
        if index:
            await asyncio.sleep(QPS_DELAY)

        data = None
        for attempt in range(3):
            try:
                data = await cj.search_products(kw, page=1, size=size)
                break
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if "Too Many Requests" in message and attempt < 2:
                    await asyncio.sleep(QPS_DELAY * (attempt + 2))
                    continue
                errors.append({"keyword": kw, "error": message[:300]})
                break
        if data is None:
            continue

        for item in _items_of(data):
            pid = str(item.get("id") or item.get("pid") or "").strip()
            if not pid:
                continue
            name = str(
                item.get("nameEn")
                or item.get("productNameEn")
                or item.get("productName")
                or ""
            ).strip()
            cost = _cost_of(item)
            if cost <= 0 or cost > max_cost:
                continue
            if strict and not is_relevant(name):
                off_niche += 1
                continue

            price = pricing_service.retail_from_cost(cost)
            # Net after PayPal fees and fixed ops cost.
            cfg = pricing_service.pricing_config()
            net = (
                price
                - (price * cfg["PAYPAL_PCT"] + cfg["PAYPAL_FIXED"])
                - cost
                - cfg["OPS_FIXED"]
            )

            prior = found.get(pid)
            row = {
                "pid": pid,
                "sku": str(item.get("sku") or "").strip(),
                "title": name,
                "cost_usd": round(cost, 2),
                "price_usd": round(price, 2),
                "profit_usd": round(net, 2),
                "margin_pct": round((net / price) * 100, 1) if price else 0.0,
                # How many CJ stores already list it — a rough demand signal.
                "listed_num": int(_f(item.get("listedNum"))),
                "has_video": bool(_f(item.get("isVedio"))),
                "image_url": item.get("bigImage") or item.get("productImage") or "",
                "category": _category_of(item),
                "owned": pid in owned_pids or name.strip().lower() in owned_titles,
                "keywords": sorted({kw} | set((prior or {}).get("keywords", []))),
            }
            found[pid] = row

    rows = [r for r in found.values() if not r["owned"]]
    if sort_by == "demand":
        rows.sort(key=lambda r: (-r["listed_num"], -r["profit_usd"]))
    else:
        rows.sort(key=lambda r: (-r["profit_usd"], -r["listed_num"]))

    return {
        "keywords": keywords,
        "already_owned": sum(1 for r in found.values() if r["owned"]),
        "candidates_found": len(rows),
        "off_niche_filtered": off_niche,
        "errors": errors,
        "top": rows[:top],
    }


def render(result: dict[str, Any]) -> None:
    if result.get("error"):
        print(f"ERROR: {result['error']}")
        return

    for err in result.get("errors", []):
        print(f"  ! {err['keyword']}: {err['error']}")

    print(
        f"\nKeywords: {len(result['keywords'])} | "
        f"new candidates: {result['candidates_found']} | "
        f"already in catalogue: {result['already_owned']} | "
        f"off-niche filtered: {result.get('off_niche_filtered', 0)}\n"
    )
    header = (
        f"{'profit':>7} {'margin':>7} {'cost':>6} {'price':>7} {'stores':>7}  title"
    )
    print(header)
    print("-" * (len(header) + 22))
    for r in result["top"]:
        video = " [video]" if r["has_video"] else ""
        print(
            f"{r['profit_usd']:>7.2f} {r['margin_pct']:>6.1f}% "
            f"{r['cost_usd']:>6.2f} {r['price_usd']:>7.2f} {r['listed_num']:>7}  "
            f"{r['title'][:56]}{video}"
        )
        print(
            f"{'':>39}  pid {r['pid']}  sku {r['sku']}  ({', '.join(r['keywords'])})"
        )
    print()


async def main() -> int:
    ap = argparse.ArgumentParser(description="Explore CJ product candidates")
    ap.add_argument("--keyword", action="append", help="Repeatable; overrides defaults")
    ap.add_argument("--size", type=int, default=20, help="Results per keyword")
    ap.add_argument("--max-cost", type=float, default=12.0, help="Max CJ unit cost USD")
    ap.add_argument("--top", type=int, default=15, help="Rows to show")
    ap.add_argument(
        "--sort",
        choices=["profit", "demand"],
        default="profit",
        help="profit = margin first; demand = most listed by other stores",
    )
    ap.add_argument(
        "--loose",
        action="store_true",
        help="Skip the niche filter (CJ search returns car mounts and clothing)",
    )
    ap.add_argument("--json", action="store_true", help="Raw JSON output")
    args = ap.parse_args()

    result = await explore(
        args.keyword or DEFAULT_KEYWORDS,
        size=args.size,
        max_cost=args.max_cost,
        top=args.top,
        sort_by=args.sort,
        strict=not args.loose,
    )
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        render(result)
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
