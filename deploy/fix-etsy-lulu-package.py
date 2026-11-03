#!/usr/bin/env python3
"""One-time fix for the unified Etsy -> Lulu worker: Lulu now requires pod_package_id inside each
line item's printable_normalization ({"line_items":{"0":{"printable_normalization":{"pod_package_id":
["This field is required."]}}}}). core.plan() only sets it on the line item, so every Etsy book order
fails with HTTP 400 and is left "uncertain".

Adds the same value inside printable_normalization (the line-level key stays), with a timestamped
backup, only if the exact original line is present once; then checks that the module still imports.
"""
import importlib.util
import shutil
import sys
import time
from pathlib import Path

CORE = Path("/opt/etsy_lulu_fulfill/lulu_books/unified/core.py")
OLD = "'printable_normalization': {'interior': {'source_url': book['interior_url']},"
NEW = "'printable_normalization': {'pod_package_id': book['pod_package_id'], 'interior': {'source_url': book['interior_url']},"

src = CORE.read_text()
if NEW in src:
    print("core.py already patched")
    sys.exit(0)
if src.count(OLD) != 1:
    print("core.py: expected line not found exactly once; not patched")
    sys.exit(1)
backup = CORE.with_name(f"core.before-pod-package-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.py")
shutil.copy2(CORE, backup)
CORE.write_text(src.replace(OLD, NEW))
spec = importlib.util.spec_from_file_location("core_check", CORE)
try:
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except Exception as exc:  # noqa: BLE001
    shutil.copy2(backup, CORE)
    print("core.py patch did not import, restored:", type(exc).__name__)
    sys.exit(1)
print("core.py patched; backup", backup.name)
