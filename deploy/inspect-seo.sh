#!/bin/bash
# One-time, read-only: how the Search Console report and the installed MCP are set up, so they can
# be extended without overwriting newer code. Prints unit definitions, file names, code outlines
# and a diff of the installed MCP against the repository copy. Credential files are shown by name
# and presence only; long key-like literals are redacted. Changes nothing.
R=/var/www/thebookswanderer.com
scrub() { sed -E 's/([A-Za-z0-9_+\/=-]{32,})/<redacted>/g'; }
echo "== units mentioning seo / search console / mcp / admin"
for u in $(systemctl list-unit-files --no-legend 2>/dev/null | awk '{print $1}' | grep -Ei 'seo|search|gsc|console|mcp|admin-api'); do
  echo "-- $u ($(systemctl is-active "$u" 2>/dev/null)/$(systemctl is-enabled "$u" 2>/dev/null))"
  systemctl cat "$u" 2>/dev/null | grep -Ev '^\s*#|^\s*$' | scrub | head -30
done
echo "== crontab lines mentioning seo / search console"
crontab -l 2>/dev/null | grep -Ei 'seo|search|gsc' | scrub
grep -rhEi 'seo|search.?console|gsc' /etc/cron.d 2>/dev/null | scrub
echo "== files mentioning searchconsole / webmasters (names only)"
grep -rlEi 'searchconsole|webmasters|search_console' /opt /etc/tbw-* /var/lib/tbw-* "$R/server" "$R/deploy" 2>/dev/null \
  | grep -v -e __pycache__ -e '/venv/' -e '/.venv/' -e site-packages | head -30
echo "== credential-like files under /etc/tbw-* (name, presence)"
find /etc/tbw-* -maxdepth 2 -type f -printf '%p  %s bytes\n' 2>/dev/null
echo "== installed MCP / admin-api code locations"
for d in /opt/tbw-mcp /opt/tbw-admin-api; do
  [ -d "$d" ] && find "$d" -maxdepth 2 -name '*.py' -not -path '*/venv/*' -not -path '*/.venv/*' -printf '%p  %s bytes  %TY-%Tm-%Td\n'
done
echo "== installed MCP vs repository copy"
for pair in "/opt/tbw-mcp/tbw_mcp.py $R/deploy/mcp/tbw_mcp.py" "/opt/tbw-admin-api/app.py $R/deploy/admin-api/app.py"; do
  set -- $pair
  [ -f "$1" ] && { echo "-- diff $1 (installed) vs repo"; diff -u "$2" "$1" | scrub | head -400; }
done
echo "== outline of Search Console code"
for f in $(grep -rlEi 'searchconsole|webmasters' /opt "$R/server" 2>/dev/null | grep -E '\.py$' | grep -v -e site-packages -e '/venv/' -e '/.venv/' -e __pycache__ | head -6); do
  echo "-- $f"
  grep -nE '^\s*(def |class |async def )|scopes|SCOPE|searchanalytics|urlInspection|sitemaps|\.json|Path\(' "$f" | scrub | head -60
done
echo "== saved report files"
find / -xdev \( -name '*seo*report*.json' -o -name '*search*console*.json' -o -name 'gsc*.json' \) -not -path '*/node_modules/*' \
  -printf '%p  %s bytes  %TY-%Tm-%Td\n' 2>/dev/null | head -10
echo "== done"
