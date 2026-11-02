#!/bin/bash
# One-time look at the existing Bonanza integration on the VPS. Never prints a secret:
# service state, file paths, and key/variable NAMES with set/empty only.
set -u
UNIT=mathrelaxing-bonanza-api
CONF=/etc/mathrelaxing-bonanza-api/bonanza.json
BRIDGE=/opt/mathrelaxing-bridge

echo "-- service $UNIT"
echo "active: $(systemctl is-active $UNIT 2>/dev/null)  enabled: $(systemctl is-enabled $UNIT 2>/dev/null)"
echo "since: $(systemctl show -p ActiveEnterTimestamp --value $UNIT 2>/dev/null)"
echo "program: $(systemctl show -p ExecStart --value $UNIT 2>/dev/null | grep -o 'path=[^ ;]*' | head -1)"
echo "user: $(systemctl show -p User --value $UNIT 2>/dev/null)"
for f in $(systemctl show -p EnvironmentFiles --value $UNIT 2>/dev/null | grep -o '/[^ ]*'); do
  echo "environment file: $f"
  [ -r "$f" ] && sed -n 's/^[ \t]*\(export[ \t]\+\)\?\([A-Za-z_][A-Za-z0-9_]*\)[ \t]*=[ \t]*\(.*\)$/\2 \3/p' "$f" |
    awk '{ v=$0; sub(/^[^ ]+ ?/, "", v); gsub(/["'\'' \t]/, "", v); printf "  %s = %s\n", $1, (v=="" ? "empty" : "set") }'
done
systemctl show -p Environment --value $UNIT 2>/dev/null | tr ' ' '\n' | grep '=' |
  awk -F= '{ printf "  env %s = %s\n", $1, ($2=="" ? "empty" : "set") }'

echo "-- $CONF (key names only)"
if [ -r "$CONF" ]; then
  python3 - "$CONF" <<'PY'
import json, sys
def walk(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            walk(v, f"{path}.{k}" if path else k)
    elif isinstance(x, list):
        print(f"  {path}: list of {len(x)}")
    else:
        print(f"  {path}: {'empty' if x in (None, '', 0, False) else 'set'} ({type(x).__name__})")
try:
    walk(json.load(open(sys.argv[1])))
except Exception as e:
    print("  not readable as JSON:", type(e).__name__)
PY
  stat -c '  owner %U:%G mode %a modified %y' "$CONF"
else
  echo "  missing or unreadable"
fi

echo "-- variables the bridge code reads (names only)"
grep -ohE "(getenv|environ(\.get)?)\(?\[?[\"'][A-Z0-9_]+[\"']" $BRIDGE/bonanza_*.py $BRIDGE/server.py 2>/dev/null |
  grep -oE "[A-Z0-9_]{3,}" | sort -u | sed 's/^/  /'
echo "-- config paths the bridge code opens"
grep -ohE "[\"']/(etc|var|opt|root)/[^\"']+[\"']" $BRIDGE/bonanza_*.py 2>/dev/null | sort -u | sed 's/^/  /'

echo "-- nginx routes for it"
grep -noE "location[ \t]+[^ {]*" /etc/nginx/conf.d/codex-api.conf 2>/dev/null | sed 's/^/  /'
grep -noE "proxy_pass[ \t]+[^;]*" /etc/nginx/conf.d/codex-api.conf 2>/dev/null | sed 's/^/  /'
echo "-- done"
