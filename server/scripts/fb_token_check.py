#!/usr/bin/env python3
"""Show what FB_PAGE_TOKEN can do, without posting anything or printing it.

  python scripts/fb_token_check.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402

GRAPH = "https://graph.facebook.com/v21.0"
token = (os.getenv("FB_PAGE_TOKEN") or "").strip()
page = (os.getenv("FB_PAGE_ID") or "").strip()
env_mtime = datetime.fromtimestamp((ROOT / ".env").stat().st_mtime, timezone.utc)
print(f".env last changed {env_mtime:%Y-%m-%d %H:%M:%S} UTC; token …{token[-4:] if token else '(empty)'}")

with httpx.Client(timeout=20) as c:
    def get(path: str, **params) -> dict:
        r = c.get(f"{GRAPH}/{path}", params={"access_token": token, **params})
        return r.json()

    print("me:", get("me", fields="id,name"))
    print("page id in .env:", page)
    d = get("debug_token", input_token=token).get("data") or get("debug_token", input_token=token)
    if isinstance(d, dict) and "scopes" in d:
        exp = d.get("expires_at") or 0
        print(f"type={d.get('type')} valid={d.get('is_valid')} app={d.get('application')} "
              f"expires={'never' if not exp else datetime.fromtimestamp(exp, timezone.utc)} profile={d.get('profile_id')}")
        print("scopes:", ", ".join(sorted(d.get("scopes", []))))
    else:
        print("debug_token:", d)
    print("page tasks:", get(page, fields="name,tasks") if page else "-")
