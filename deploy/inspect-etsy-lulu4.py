#!/usr/bin/env python3
"""One-time, read-only, no network: why Lulu answers HTTP 400 to the print job for receipt 4220948340.
Prints the SHAPE of the prepared payload (key, present/empty, length, never values except fixed
codes like shipping_level, pod_package_id, country), the config settings that feed it (names and
set/empty), and the worker functions that build and send it (key-like literals redacted)."""
import ast
import json
import re
from pathlib import Path

RID = "4220948340"
UNIFIED = Path("/opt/etsy_lulu_fulfill/lulu_books/unified")
SAFE = {"shipping_level", "pod_package_id", "country_code", "state_code", "quantity", "page_count", "external_id", "currency"}
TOKENISH = re.compile(r"(['\"])([A-Za-z0-9_\-+/=.]{24,})\1")


def shape(v, key=""):
    if isinstance(v, dict):
        return {k: shape(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [shape(x, key) for x in v[:3]]
    if key in SAFE:
        return v
    if isinstance(v, str):
        return f"str[{len(v)}]" if v.strip() else "EMPTY"
    return type(v).__name__ if v is not None else "None"


config = json.loads((UNIFIED / "config.json").read_text())
cfg = json.loads(Path(config["state_dir"], "state.json").read_text())
entry = cfg["receipts"].get(RID, {})
payload = entry.get("payload") or {}
print("== payload shape for", RID, "status", entry.get("status"))
print(json.dumps(shape(payload), indent=1)[:3000])
print("== config settings (names, set/empty or fixed values)")
for k, v in sorted(config.get("settings", {}).items()):
    shown = v if isinstance(v, (bool, int, float)) or k in SAFE else ("set" if v else "empty")
    print(f"  {k}: {shown}")
print("  top-level keys:", sorted(config.keys()))
for name in ("worker.py", "core.py"):
    src = (UNIFIED / name).read_text(errors="replace")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
                "lulu", "create", "payload", "build_payload", "plan", "address", "shipping_address", "lulu_address"):
            print(f"-- {name}:{node.name} (lines {node.lineno}-{node.end_lineno})")
            print(TOKENISH.sub(lambda m: m.group(1) + "<redacted>" + m.group(1),
                               "\n".join(lines[node.lineno - 1:node.end_lineno]))[:4000])
print("== done")
