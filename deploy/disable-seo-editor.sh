#!/bin/bash
# One-time, owner-requested (2026-11-03): disable the autonomous editorial pilot (tbw-seo-editor)
# and report, read-only, what it did. Its files, state and published pages are left in place.
scrub() { sed -E 's/([A-Za-z0-9_+\/=-]{32,})/<redacted>/g; s/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/<email>/g'; }
echo "== disable"
systemctl disable --now tbw-seo-editor.timer 2>&1 | tail -2
systemctl stop tbw-seo-editor.service 2>/dev/null
systemctl reset-failed tbw-seo-editor.service 2>/dev/null
echo "timer: $(systemctl is-enabled tbw-seo-editor.timer 2>/dev/null)/$(systemctl is-active tbw-seo-editor.timer 2>/dev/null)  service: $(systemctl is-active tbw-seo-editor.service 2>/dev/null)"
echo "== runs (journal, last 60 lines)"
journalctl -u tbw-seo-editor.service --no-pager -o short-iso -n 60 2>/dev/null | scrub | cut -c1-400
echo "== published pages by the pilot"
ls -ld --time-style=+%F\ %R /var/www/thebookswanderer.com/guides/editor-* /var/www/thebookswanderer.com/guides/editor* 2>/dev/null | sort -u
for f in /var/www/thebookswanderer.com/guides/editor-*/index.html; do
  [ -f "$f" ] && echo "  $(grep -o '<title>[^<]*' "$f" | head -1 | sed 's/<title>//')  [$f]"
done
echo "== state folder (names, sizes)"
find /var/lib/tbw-seo-editor -maxdepth 2 -printf '%y %8s  %TY-%Tm-%Td %TH:%TM  %P\n' 2>/dev/null | sort -k4 | tail -40
DB=/var/lib/tbw-seo-editor/editor.db
if [ -f "$DB" ]; then
  echo "== editor.db tables and counts"
  python3 - "$DB" <<'PY'
import sqlite3, sys
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
for (t,) in db.execute("select name from sqlite_master where type='table'"):
    cols = [c[1] for c in db.execute(f"pragma table_info('{t}')")]
    n = db.execute(f"select count(*) from '{t}'").fetchone()[0]
    print(f"-- {t} ({n} rows): {', '.join(cols)}")
    keep = [c for c in cols if c in ("id","month","purpose","status","state","reserved_usd","cost","slug","url","title","created_at","updated_at","error","reason","week","lang")]
    if keep:
        for row in db.execute(f"select {','.join(keep)} from '{t}' order by rowid desc limit 12"):
            print("   ", dict(zip(keep, [str(v)[:160] for v in row])))
PY
fi
echo "== config keys (values hidden except booleans/numbers)"
python3 - <<'PY'
import json
try:
    c = json.load(open("/etc/tbw-seo-editor/config.json"))
    for k, v in sorted(c.items()):
        print(f"  {k}: {v if isinstance(v, (bool, int, float)) else ('set' if v else 'empty')}")
except Exception as e:
    print("  config unreadable:", type(e).__name__)
PY
echo "== done"
