#!/usr/bin/env python3
"""List which credentials exist on the server, by name only: never prints a value.

  python scripts/env_names.py bonanza          # names containing "bonanza", case-insensitive

Looks in server/.env and in the process environment. For each match prints the name and
whether it holds a value (set / empty).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    needle = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if not needle:
        print("usage: env_names.py PATTERN")
        return 2
    found = {}
    env_file = ROOT / ".env"
    if env_file.is_file():
        for name, value in dotenv_values(env_file).items():
            if needle in name.lower():
                found[name] = ("server/.env", bool((value or "").strip()))
    for name, value in os.environ.items():
        if needle in name.lower() and name not in found:
            found[name] = ("environment", bool(value.strip()))
    if not found:
        print(f"no variable names contain {needle!r}")
    for name, (where, has_value) in sorted(found.items()):
        print(f"{name} ({where}): {'set' if has_value else 'empty'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
