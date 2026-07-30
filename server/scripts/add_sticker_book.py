"""Add CJYD2138789 (all 6 design variants) to the live catalog."""
from __future__ import annotations

import json
import urllib.request

import os
import sys

ADMIN_KEY = os.environ.get("TBW_ADMIN_KEY", "")
BASE = os.environ.get("TBW_BASE", "https://thebookswanderer.com")
if not ADMIN_KEY:
    raise SystemExit("Set TBW_ADMIN_KEY")
PID = "2409160535121624500"
PRICE = 8.99
CATEGORY = "Journaling"

VARIANTS = [
    ("2409160535121624700", "White Dew Xifeng", "washi-sticker-white-dew-xifeng"),
    ("2409160535121624800", "Nanmu Wind", "washi-sticker-nanmu-wind"),
    ("2409160535121625000", "Song Of Mu Xia", "washi-sticker-song-of-mu-xia"),
    ("2409160535121625100", "Butterfly Dream Zhuang Zhou", "washi-sticker-butterfly-dream"),
    ("2409160535121625300", "Mushroom Nocturne", "washi-sticker-mushroom-nocturne"),
    ("2409160535121625400", "Late Autumn Evening Wind", "washi-sticker-late-autumn"),
]

DESC = (
    "Retro Japanese-style washi sticker book for journals and planners. "
    "About 50 sheets per book — soft vintage designs for readers who decorate their pages."
)


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main() -> None:
    import time

    only = sys.argv[1:]  # optional slug filters
    for vid, design, slug in VARIANTS:
        if only and slug not in only and design not in only:
            continue
        title = f"Washi Sticker Book — {design}"
        body = {
            "admin_key": ADMIN_KEY,
            "cj_pid": PID,
            "cj_vid": vid,
            "title": title,
            "description": DESC,
            "category": CATEGORY,
            "price_usd": PRICE,
            "slug": slug,
        }
        try:
            res = post("/api/admin/products", body)
            p = res.get("product") or {}
            print(
                "OK",
                p.get("id"),
                p.get("slug"),
                p.get("price_usd"),
                (p.get("image_url") or "")[:50],
            )
        except Exception as exc:
            print("FAIL", design, exc)
        time.sleep(1.2)  # CJ QPS limit


if __name__ == "__main__":
    main()
