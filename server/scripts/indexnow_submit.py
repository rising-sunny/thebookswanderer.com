#!/usr/bin/env python3
"""IndexNow: tell Bing (and Yandex, Seznam, Naver, which share submissions)
about new or changed pages right away instead of waiting for a crawl.

Reads the live sitemap and submits the URLs whose <lastmod> changed since the
last run (state in data/indexnow_state.json). The key file sits in the web
root as <key>.txt; the key is public by design. Cron runs it daily.

  python scripts/indexnow_submit.py            # new / changed URLs
  python scripts/indexnow_submit.py --all      # every URL in the sitemap
  python scripts/indexnow_submit.py --dry-run  # list only
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import DATA_DIR  # noqa: E402

KEY = "c8e661e720274c3e3e3035210af1a952"
ENDPOINT = "https://api.indexnow.org/indexnow"
STATE = DATA_DIR / "indexnow_state.json"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
BATCH = 10000  # protocol maximum per request


def base() -> str:
    return os.getenv("PUBLIC_BASE_URL", "https://thebookswanderer.com").rstrip("/")


def sitemap() -> dict[str, str]:
    r = httpx.get(f"{base()}/sitemap.xml", timeout=30, follow_redirects=True)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = {}
    for u in root.findall("s:url", NS):
        loc = (u.findtext("s:loc", "", NS) or "").strip()
        if loc:
            out[loc] = (u.findtext("s:lastmod", "", NS) or "").strip()
    return out


def main() -> int:
    dry, every = "--dry-run" in sys.argv, "--all" in sys.argv
    host = urlparse(base()).netloc
    key_url = f"{base()}/{KEY}.txt"
    check = httpx.get(key_url, timeout=15)
    if check.status_code != 200 or check.text.strip() != KEY:
        print(f"key file not served at {key_url} ({check.status_code}); not submitting")
        return 1
    urls = sitemap()
    seen = {} if every or not STATE.exists() else json.loads(STATE.read_text())
    todo = [u for u, mod in urls.items() if urlparse(u).netloc == host and seen.get(u) != mod]
    print(f"sitemap {len(urls)} urls, {len(todo)} new or changed")
    if dry or not todo:
        for u in todo[:50]:
            print("  ", u)
        return 0
    for i in range(0, len(todo), BATCH):
        r = httpx.post(ENDPOINT, timeout=30, json={
            "host": host, "key": KEY, "keyLocation": key_url, "urlList": todo[i:i + BATCH]})
        # 200 = received, 202 = received, key validation pending
        print(f"submitted {len(todo[i:i + BATCH])}: HTTP {r.status_code} {r.text[:200]}")
        if r.status_code not in (200, 202):
            return 1
    STATE.write_text(json.dumps(urls, indent=0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
