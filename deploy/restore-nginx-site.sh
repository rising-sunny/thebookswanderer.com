#!/bin/bash
# Rebuild /etc/nginx/sites-available/thebookswanderer.com after it was emptied (0 bytes), and prove the
# rebuilt file behaves like the configuration nginx is still running from memory BEFORE installing it.
#
#   sudo bash deploy/restore-nginx-site.sh             # build + test on a second nginx + compare; installs nothing
#   sudo bash deploy/restore-nginx-site.sh --install   # same, and if everything matches, writes the file
#
# How the file is rebuilt: the Oct 10 backup (sites-available/thebookswanderer.com.bak-20261010-181211,
# md5 prefix 60ebfc8f) plus what was added later: the /server and /deploy 404 blocks, the three chained
# snippet includes, and the real patchers from deploy/remote-setup.sh (/es/, /admin/digital/,
# /admin/product-media/). The result is checked against the line map of the original file.
#
# The test instance is a copy of the main nginx.conf without the conf.d / sites-enabled includes, listening
# on 127.0.0.1:28443 (HTTPS) and :28080, so it cannot collide with the running nginx. It is stopped at exit.
# This script never reloads or restarts the real nginx: the running configuration already equals the file.
set -euo pipefail

INSTALL=0
[ "${1:-}" = "--install" ] && INSTALL=1

BASE="${TBW_RESTORE_BASE:-/etc/nginx/sites-available/thebookswanderer.com.bak-20261010-181211}"
TARGET="${TBW_RESTORE_TARGET:-/etc/nginx/sites-available/thebookswanderer.com}"
SNIPPETS="${TBW_RESTORE_SNIPPETS:-/etc/nginx/snippets}"
MAIN_CONF="${TBW_RESTORE_MAIN_CONF:-/etc/nginx/nginx.conf}"
SETUP="${TBW_RESTORE_SETUP:-/var/www/thebookswanderer.com/deploy/remote-setup.sh}"
NGINX="${TBW_NGINX_BIN:-nginx}"
LIVE_PORT="${TBW_LIVE_PORT:-443}"
TEST_PORT="${TBW_TEST_PORT:-28443}"      # ports in use on the VPS include 8080, 8443-ish tools: pick high ones
TEST_HTTP="${TBW_TEST_HTTP_PORT:-28080}"
CURL_EXTRA="${TBW_CURL_EXTRA:-}"
EXPECT_MD5="${TBW_RESTORE_BASE_MD5:-60ebfc8f}"
SAVE_DIR="${TBW_RESTORE_SAVE_DIR:-/root}"
HOST=thebookswanderer.com
# Line numbers of server_name/listen/add_header/location/limit_req/include lines in the ORIGINAL file.
EXPECT_MAP="7 15 24 25 26 27 37 38 39 41 51 71 80 90 100 109 119 128 137 146 156 165 175 186 196 200 201 203 204 205 210 214 215 218 221 222 223 240 241 242"

fail() { echo "STOP: $*" >&2; exit 1; }
WORK=$(mktemp -d)
cleanup() {
  [ -f "$WORK/nginx.pid" ] && "$NGINX" -c "$WORK/nginx.conf" -s stop >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "== 1. Preconditions"
[ -f "$BASE" ] || fail "base backup not found: $BASE"
[ "$(md5sum < "$BASE" | cut -c1-8)" = "$EXPECT_MD5" ] || fail "base backup md5 is not $EXPECT_MD5: it is not the file this script was written for"
REAL=$(readlink -f "$TARGET")
if [ -s "$REAL" ] && [ "${TBW_RESTORE_FORCE:-0}" != "1" ]; then
  fail "$REAL is not empty ($(wc -c < "$REAL") bytes). Nothing to restore."
fi
for s in tbw-social-publisher tbw-admin-api tbw-mcp; do
  [ -f "$SNIPPETS/$s.conf" ] || fail "missing snippet $SNIPPETS/$s.conf"
done
[ -f "$SETUP" ] || fail "missing $SETUP"
echo "   base ok, target is empty, snippets and remote-setup.sh present"

echo "== 2. Build the candidate"
python3 - "$BASE" "$SETUP" "$WORK/site.conf" <<'PY'
import re, subprocess, sys
from pathlib import Path
base, setup, out = sys.argv[1:4]
text = Path(base).read_text(encoding="utf-8")
blk404 = """    # Never serve repository internals
    location = /server { return 404; }
    location ^~ /server/ { return 404; }
    location = /deploy { return 404; }
    location ^~ /deploy/ { return 404; }

"""
incs = """
    # Local services (installed by deploy/admin-api and deploy/mcp)
    include /etc/nginx/snippets/tbw-social-publisher.conf;
    include /etc/nginx/snippets/tbw-admin-api.conf;
    include /etc/nginx/snippets/tbw-mcp.conf;
"""
for anchor, add in (("    # gzip text assets\n", blk404), ("    # Store API (CJ + PayPal)\n", incs)):
    if text.count(anchor) != 1:
        sys.exit(f"anchor not found exactly once: {anchor!r}")
    text = text.replace(anchor, add + anchor)
Path(out).write_text(text, encoding="utf-8")
rs = Path(setup).read_text()
for marker in ("location /es/", "location /admin/digital/", "location \\^~ /admin/product-media/"):
    m = re.search(r"if \[ -f \"\$CONF\" \] && ! grep -q '" + re.escape(marker) + r"' \"\$CONF\"; then\n  python3 - <<'PY'\n(.*?)\nPY\n", rs, re.S)
    if not m:
        sys.exit(f"patcher for {marker} not found in {setup}")
    # run the real patcher on the candidate; its own nginx -t checks the machine, not the candidate, so skip it here
    code = m.group(1).replace("/etc/nginx/sites-enabled/thebookswanderer.com", out).replace('["nginx", "-t"]', '["true"]')
    r = subprocess.run(["python3", "-c", code], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"patcher failed for {marker}: {r.stdout}{r.stderr}")
    print("   " + (r.stdout.strip() or marker))
PY
GOT=$(grep -n "server_name\|listen\|add_header\|location\|limit_req\|include" "$WORK/site.conf" | cut -d: -f1 | tr '\n' ' ' | sed 's/ $//')
[ "$GOT" = "$EXPECT_MAP" ] || { echo "   expected: $EXPECT_MAP"; echo "   got:      $GOT"; fail "the rebuilt file does not match the line map of the original"; }
echo "   line map matches the original file ($(wc -l < "$WORK/site.conf") lines)"

echo "== 3. Start a second nginx on 127.0.0.1:$TEST_PORT with the candidate"
sed -E -e "s|^[[:space:]]*listen[[:space:]]+\[::\]:443[^;]*;.*$|    # (ipv6 listen removed for the test instance)|" \
       -e "s|^[[:space:]]*listen[[:space:]]+443[[:space:]]+ssl[[:space:]]+http2;.*$|    listen 127.0.0.1:$TEST_PORT ssl http2;|" \
       -e "s|^[[:space:]]*listen[[:space:]]+\[::\]:80;.*$|    # (ipv6 listen removed)|" \
       -e "s|^[[:space:]]*listen[[:space:]]+80;.*$|    listen 127.0.0.1:$TEST_HTTP;|" \
       "$WORK/site.conf" > "$WORK/test-site.conf"
# Keep the default nginx prefix (so load_module paths resolve) and make relative includes absolute,
# because -c moves the configuration prefix to the directory of the test file.
sed -E -e '/include[[:space:]]+\/etc\/nginx\/(sites-enabled|conf\.d)\//d' \
       -e 's|^([[:space:]]*include[[:space:]]+)([^/;[:space:]][^;]*);|\1/etc/nginx/\2;|' \
       -e '/^[[:space:]]*(pid|error_log)[[:space:]]/d' \
       -e 's|^([[:space:]]*)access_log[[:space:]].*;|\1access_log off;|' \
       -e "s|^([[:space:]]*)http[[:space:]]*\{|\1http {\n    include $WORK/test-site.conf;|" \
       "$MAIN_CONF" > "$WORK/nginx.conf.body"
{ echo "pid $WORK/nginx.pid;"; echo "error_log $WORK/error.log warn;"; cat "$WORK/nginx.conf.body"; } > "$WORK/nginx.conf"
"$NGINX" -t -c "$WORK/nginx.conf" || fail "nginx -t failed for the test instance (details above)"
"$NGINX" -c "$WORK/nginx.conf"
sleep 1

echo "== 4. Compare the test instance with the live site (status, headers, and bodies of static files)"
PATHS="/ /index.html /sitemap.xml /robots.txt /styles.css /app.js /checkout.js /reading-challenge-2027/ /reto-de-lectura-2027/ /guides/gifts-for-book-lovers/ /guides/assets/journal.css /assets/logo.png /assets/products/reading-challenge-journal-2027/main.jpg /products/reading-challenge-journal-2027 /es/ /es /es/products/reading-challenge-journal-2027 /collections /collections/ /picks/x /product.html /pick.html /api/health /api/products?limit=1 /admin/live /admin/live/login /admin/digital/x /admin/product-media/ /.env /.git/HEAD /.well-known/security.txt /server /server/main.py /deploy/DEPLOY.md /deploy /no-existe-xyz /about.html /privacy.html"
# also the plain prefixes served by the three snippets (status and headers only)
SNIP=$(grep -hoE "location[[:space:]]+(=|\^~)?[[:space:]]*/[^[:space:]{]*" "$SNIPPETS"/tbw-social-publisher.conf "$SNIPPETS"/tbw-admin-api.conf "$SNIPPETS"/tbw-mcp.conf 2>/dev/null | sed -E 's/^location[[:space:]]+(=|\^~)?[[:space:]]*//' | sort -u | tr '\n' ' ')
BODYPATHS=" /robots.txt /styles.css /app.js /checkout.js /reading-challenge-2027/ /reto-de-lectura-2027/ /guides/gifts-for-book-lovers/ /guides/assets/journal.css /assets/logo.png /about.html /privacy.html /.env /server /deploy "
probe() {  # $1 port  $2 path -> "status|content-type|location|cache-control|hsts|bodymd5"
  local code hdr
  rm -f "$WORK/body" "$WORK/hdr"
  if ! code=$(curl -sS --noproxy '*' -o "$WORK/body" -D "$WORK/hdr" -w '%{http_code}' --max-time 20 $CURL_EXTRA \
         --resolve "$HOST:$1:127.0.0.1" "https://$HOST:$1$2" 2>/dev/null); then code="ERR"; fi
  hdr=$(tr -d '\r' < "$WORK/hdr" 2>/dev/null | tr 'A-Z' 'a-z')
  h() { printf '%s' "$hdr" | grep -m1 "^$1:" | cut -d: -f2- | sed 's/^ //' || true; }
  local sum="-"
  case "$BODYPATHS" in *" $2 "*) [ -f "$WORK/body" ] && sum=$(md5sum < "$WORK/body" | cut -c1-12) ;; esac
  echo "$code|$(h content-type)|$(h location)|$(h cache-control)|$(h strict-transport-security)|$sum"
}
BAD=0; N=0
for p in $PATHS $SNIP; do
  N=$((N+1))
  live=$(probe "$LIVE_PORT" "$p"); test=$(probe "$TEST_PORT" "$p")
  # Two identical FAILURES must never count as a match: both sides have to answer with a real HTTP status.
  case "$live" in 000\|*|ERR*) fail "the live site did not answer on 127.0.0.1:$LIVE_PORT for $p (is TBW_LIVE_PORT right?)";; esac
  case "$test" in 000\|*|ERR*) fail "the test instance did not answer on 127.0.0.1:$TEST_PORT for $p";; esac
  if [ "$live" != "$test" ]; then
    BAD=$((BAD+1)); echo "   DIFF $p"; echo "        live: $live"; echo "        test: $test"
  fi
done
echo "   compared $N URLs, $BAD differ"
[ "$BAD" -eq 0 ] || fail "the rebuilt file does not behave like the live configuration. Nothing was installed."

if [ "$INSTALL" -ne 1 ]; then
  echo; echo "OK: the rebuilt file behaves like the live site. Re-run with --install to write it."; exit 0
fi

echo "== 5. Install"
mkdir -p "$SAVE_DIR"
KEEP="$SAVE_DIR/thebookswanderer.com.restored-$(date +%Y%m%d-%H%M%S)"
cp -p "$WORK/site.conf" "$KEEP"
cp "$WORK/site.conf" "$REAL.tbw-new" && mv -f "$REAL.tbw-new" "$REAL"
echo "   written to $REAL (extra copy: $KEEP)"
if "$NGINX" -t; then
  echo "OK: nginx -t passes with the restored file. The running nginx already matches it, so no reload is needed."
else
  echo "WARNING: nginx -t fails with the restored file (details above). The file is written; a copy is in $KEEP." >&2
  exit 1
fi
