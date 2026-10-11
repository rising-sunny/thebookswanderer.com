#!/usr/bin/env python3
"""Print the daily social post log and the last state entries (read-only).

  python scripts/social_log.py [lines]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = Path("/var/log/tbw-social.log")
STATE = ROOT / "data" / "social_posts.json"

lines = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 80
print(f"── {LOG} (last {lines} lines) ──")
try:
    print("".join(LOG.read_text(errors="replace").splitlines(True)[-lines:]))
except OSError as exc:
    print(f"cannot read: {exc}")
print(f"── {STATE} (last 5 entries) ──")
try:
    print(json.dumps(json.loads(STATE.read_text())[-5:], indent=1))
except (OSError, ValueError) as exc:
    print(f"cannot read: {exc}")
