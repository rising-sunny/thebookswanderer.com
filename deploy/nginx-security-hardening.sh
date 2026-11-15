#!/bin/bash
# Security headers + request rate limits for thebookswanderer.com (nginx).
#
#   sudo bash deploy/nginx-security-hardening.sh            # dry run: shows the diff, changes nothing
#   sudo bash deploy/nginx-security-hardening.sh --apply    # backs up, writes, nginx -t, reload; restores on failure
#
# Adds (idempotent):
#   /etc/nginx/snippets/tbw-security-headers.conf  nosniff, X-Frame-Options, Referrer-Policy,
#                                                  Permissions-Policy, a CSP that only sets
#                                                  frame-ancestors / base-uri / object-src
#   /etc/nginx/conf.d/tbw-ratelimit.conf           per-IP limits: newsletter sign-up 5/min,
#                                                  admin login 10/min, /api/ 10/s (burst 60);
#                                                  429 and log level are set in the server block
# and patches the site file so that the server block and every location that repeats the HSTS
# header (nginx only inherits add_header into a location that defines none) also include the headers.
set -euo pipefail

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

SITE="${TBW_NGINX_SITE:-/etc/nginx/sites-enabled/thebookswanderer.com}"
HEADERS="${TBW_NGINX_HEADERS:-/etc/nginx/snippets/tbw-security-headers.conf}"
RATE="${TBW_NGINX_RATE:-/etc/nginx/conf.d/tbw-ratelimit.conf}"
TEST_CMD="${TBW_NGINX_TEST:-nginx -t}"
RELOAD_CMD="${TBW_NGINX_RELOAD:-systemctl reload nginx}"

[ -f "$SITE" ] || { echo "Not found: $SITE" >&2; exit 1; }
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/headers.conf" <<'EOF'
# Security headers for thebookswanderer.com. Included at server level and in any location that
# repeats the HSTS header (a location with its own add_header does not inherit the server's).
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
add_header Content-Security-Policy "frame-ancestors 'self'; base-uri 'self'; object-src 'none'" always;
EOF

cat > "$WORK/ratelimit.conf" <<'EOF'
# Per-IP request limits. A map gives an empty key to every other URL, and an empty key is not counted.
map $request_uri $tbw_k_newsletter { default ""; ~^/api/newsletter/subscribe $binary_remote_addr; }
map $request_uri $tbw_k_login      { default ""; ~^/admin/live/login        $binary_remote_addr; }
map $request_uri $tbw_k_api        { default ""; ~^/api/                    $binary_remote_addr; }

limit_req_zone $tbw_k_newsletter zone=tbw_newsletter:10m rate=5r/m;
limit_req_zone $tbw_k_login      zone=tbw_login:10m      rate=10r/m;
limit_req_zone $tbw_k_api        zone=tbw_api:10m        rate=10r/s;
# limit_req_status / limit_req_log_level are set in the site's server block, not here: other config
# on the host may already set them at http level, and nginx rejects a duplicate in the same context.
EOF

python3 - "$SITE" "$WORK/site.new" "$HEADERS" <<'PY'
import sys
site, out, headers = sys.argv[1:4]
HSTS = 'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;'
INCLUDE = f"include {headers};"
LIMITS = [
    "limit_req_status 429;",
    "limit_req_log_level warn;",
    "limit_req zone=tbw_newsletter burst=3 nodelay;",
    "limit_req zone=tbw_login burst=5 nodelay;",
    "limit_req zone=tbw_api burst=60 nodelay;",
]
lines = open(site, encoding="utf-8").read().split("\n")
if any(INCLUDE in l for l in lines):
    open(out, "w", encoding="utf-8").write("\n".join(lines)); print("site file already patched"); sys.exit(0)
res, server_level, loc_level = [], 0, 0
for l in lines:
    res.append(l)
    if l.strip() == HSTS:
        indent = l[: len(l) - len(l.lstrip())]
        res.append(f"{indent}{INCLUDE}")
        if len(indent) == 4:                      # the HTTPS server block itself
            server_level += 1
            res.append(f"{indent}# Request limits (zones in conf.d/tbw-ratelimit.conf); empty keys are never counted.")
            res += [f"{indent}{x}" for x in LIMITS]
        else:
            loc_level += 1
if server_level != 1:
    sys.exit(f"ABORT: expected exactly one server-level HSTS line, found {server_level}")
open(out, "w", encoding="utf-8").write("\n".join(res))
print(f"patched: 1 server-level include + {loc_level} location-level include(s)")
PY

echo "=== Diff of the site file"; diff -u "$SITE" "$WORK/site.new" || true
echo "=== Files to create"; echo "  $HEADERS"; echo "  $RATE"
echo "=== add_header already present in the included snippets (informational):"
grep -Hn "add_header" /etc/nginx/snippets/tbw-*.conf 2>/dev/null | grep -v "tbw-security-headers" || echo "  none"

if [ "$APPLY" -ne 1 ]; then
  echo; echo "Dry run only. Re-run with --apply to write the files, test and reload nginx."; exit 0
fi

BK="/root/nginx-backup-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$BK"
cp -a "$SITE" "$BK/site.conf"
for f in "$HEADERS" "$RATE"; do [ -f "$f" ] && cp -a "$f" "$BK/$(basename "$f").old" || true; done
mkdir -p "$(dirname "$HEADERS")" "$(dirname "$RATE")"
install -m 644 "$WORK/headers.conf" "$HEADERS"
install -m 644 "$WORK/ratelimit.conf" "$RATE"
cat "$WORK/site.new" > "$SITE"

if $TEST_CMD; then
  $RELOAD_CMD
  echo "OK: nginx reloaded. Backup in $BK"
else
  echo "nginx -t FAILED: restoring the backup" >&2
  cat "$BK/site.conf" > "$SITE"
  [ -f "$BK/$(basename "$HEADERS").old" ] && install -m 644 "$BK/$(basename "$HEADERS").old" "$HEADERS" || rm -f "$HEADERS"
  [ -f "$BK/$(basename "$RATE").old" ] && install -m 644 "$BK/$(basename "$RATE").old" "$RATE" || rm -f "$RATE"
  $TEST_CMD >/dev/null 2>&1 && echo "Restored; nginx config is valid again." >&2
  exit 1
fi
