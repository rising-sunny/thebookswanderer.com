#!/usr/bin/env python3
"""One-time, read-only follow-up: which books the unified Etsy -> Lulu worker knows (listing ids and
status only), its state folder and log mentions of the puzzle book order, and this store's own
registration record for it. Buyer data is filtered as in inspect-etsy-lulu.py."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
cat = json.loads(Path("/opt/etsy_lulu_fulfill/lulu_books/unified/catalog.json").read_text())
books = cat.get("books", cat) if isinstance(cat, dict) else cat
print("== unified catalog: books")
items = books.items() if isinstance(books, dict) else enumerate(books)
for key, b in items:
    if isinstance(b, dict):
        keep = {k: v for k, v in b.items() if isinstance(v, (str, int, float, bool)) and len(str(v)) < 80
                and any(w in k.lower() for w in ("listing", "sku", "status", "state", "active", "title", "slug", "hold", "id"))}
        print(f"  {key}: {json.dumps(keep, ensure_ascii=False)[:300]}")
print("== registration requests in the config/state")
for f in [Path("/opt/etsy_lulu_fulfill/lulu_books/unified/config.json")]:
    c = json.loads(f.read_text())
    print("  config keys:", sorted(c.keys()))
reg = Path("/var/www/thebookswanderer.com/server/data/etsy_lulu_registrations.json")
if reg.is_file():
    data = json.loads(reg.read_text())
    print("== this store's registrations:")
    for k, v in (data.items() if isinstance(data, dict) else enumerate(data)):
        flat = {kk: vv for kk, vv in (v.items() if isinstance(v, dict) else []) if isinstance(vv, (str, int, float, bool)) and len(str(vv)) < 120}
        print(f"  {k}: {json.dumps(flat, ensure_ascii=False)[:400]}")
sys.stdout.flush()
subprocess.run([sys.executable, str(HERE / "inspect-etsy-lulu.py"), "/var/lib/mathrelaxing-etsy-lulu"], timeout=120)
