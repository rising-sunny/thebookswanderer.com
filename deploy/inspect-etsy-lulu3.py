#!/usr/bin/env python3
"""One-time, read-only: how the unified Etsy -> Lulu worker handles an "uncertain" submission and how
an operator is meant to resolve it. Prints the worker's commands, the functions that mention
uncertain/reconcile/retry (long key-like literals redacted), the receipt's state fields without
buyer data, and the first log lines (masked). Changes nothing."""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

UNIFIED = Path("/opt/etsy_lulu_fulfill/lulu_books/unified")
STATE = Path("/var/lib/mathrelaxing-etsy-lulu/state.json")
LOG = Path("/var/lib/mathrelaxing-etsy-lulu/worker.log")
RECEIPT = "4220948340"
TOKENISH = re.compile(r"(['\"])([A-Za-z0-9_\-+/=.]{24,})\1")
PII_KEY = re.compile(r"(?i)(name|address|street|line_?\d|first_line|second_line|city|zip|post|email|phone|buyer|recipient|customer|tax_id|message)")
sys.path.insert(0, str(Path(__file__).parent))


def scrub(text):
    return TOKENISH.sub(lambda m: m.group(1) + "<redacted>" + m.group(1), text)


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items() if not PII_KEY.search(str(k)) and k not in ("payload",)}
    if isinstance(v, list):
        return [clean(x) for x in v[:10]]
    return v


for name in ("worker.py", "core.py"):
    f = UNIFIED / name
    src = f.read_text(errors="replace")
    tree = ast.parse(src)
    lines = src.splitlines()
    print(f"== {name}: {len(lines)} lines")
    doc = ast.get_docstring(tree)
    if doc:
        print(scrub(doc[:800]))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("add_parser", "add_argument"):
            seg = ast.get_source_segment(src, node) or ""
            print("  cli:", scrub(seg)[:200])
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = "\n".join(lines[node.lineno - 1:node.end_lineno])
            if re.search(r"uncertain|reconcil|retry|resolve|preserv", seg, re.I) and len(seg) < 7000:
                print(f"-- {name}:{node.name} (lines {node.lineno}-{node.end_lineno})")
                print(scrub(seg))
state = json.loads(STATE.read_text())
rec = (state.get("receipts") or {}).get(RECEIPT, {})
print("== state for the receipt (no buyer data, no payload)")
print(json.dumps(clean(rec), ensure_ascii=False, default=str)[:2000])
print("== state top-level keys:", sorted(state.keys()))
log = LOG.read_text(errors="replace").splitlines()
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CAP = re.compile(r"\b[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+){1,3}\b")
print(f"== worker.log ({len(log)} lines), first 8")
for l in log[:8]:
    print("   ", CAP.sub("<name>", EMAIL.sub("<email>", l))[:400])
print("== done")
