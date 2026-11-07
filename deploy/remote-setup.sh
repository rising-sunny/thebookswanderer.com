#!/bin/bash
set -e
REMOTE_PATH=/var/www/thebookswanderer.com
cd "$REMOTE_PATH/server"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  SECRET=$(openssl rand -hex 24)
  {
    echo "APP_ENV=production"
    echo "PUBLIC_BASE_URL=https://thebookswanderer.com"
    echo "SECRET_KEY=$SECRET"
    echo "MARKUP_MULTIPLIER=2.4"
    echo "SHIPPING_MARKUP=1.15"
    echo "CJ_PAY_TYPE=3"
    echo "CJ_API_KEY="
    echo "PAYPAL_MODE=live"
  } > .env
  if [ -f /var/www/mathrelaxing.store/.env ]; then
    grep -E '^(PAYPAL_CLIENT_ID|PAYPAL_SECRET|PAYPAL_MODE|PAYPAL_WEBHOOK_ID)=' \
      /var/www/mathrelaxing.store/.env >> .env || true
  fi
  echo "Created server/.env"
fi

# Ensure CJ key line exists (do not overwrite if already set)
if ! grep -q '^CJ_API_KEY=.\+' .env; then
  echo "NOTE: set CJ_API_KEY in $REMOTE_PATH/server/.env"
fi

chown -R www-data:www-data "$REMOTE_PATH"
# scp refreshes guides permissions and the recursive chown above changes generated
# ownership. Restore the installed editor's publication area after every deploy.
if id tbw-editor >/dev/null 2>&1; then
  chgrp www-data "$REMOTE_PATH/guides"
  chmod g+ws "$REMOTE_PATH/guides"
  find "$REMOTE_PATH/guides" -mindepth 1 -maxdepth 1 -type d -name 'editor-*' \
    -exec chown -R --no-dereference tbw-editor:www-data {} +
fi
chmod 640 "$REMOTE_PATH/server/.env" || true
chmod 755 "$REMOTE_PATH/server/data"
# www-data needs write for sqlite
chown www-data:www-data "$REMOTE_PATH/server/data"

# Product galleries: public immutable uploads and private before/after backups.
install -d -o www-data -g www-data -m 755 "$REMOTE_PATH/assets/products/uploads"
install -d -o www-data -g www-data -m 700 /var/lib/tbw-product-media

# Professional-contact research must never live under the public web root.
mkdir -p /var/lib/tbw-collaborators
chown www-data:www-data /var/lib/tbw-collaborators
chmod 700 /var/lib/tbw-collaborators

systemctl daemon-reload
systemctl enable thebookswanderer.service
systemctl restart thebookswanderer.service
sleep 2
systemctl is-active thebookswanderer.service
curl -sS http://127.0.0.1:8010/api/health
echo

# nginx /api proxy if missing
CONF=/etc/nginx/sites-enabled/thebookswanderer.com
if [ -f "$CONF" ] && ! grep -q '127.0.0.1:8010' "$CONF"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/etc/nginx/sites-enabled/thebookswanderer.com")
text = p.read_text()
block = """
    # Store API (CJ + PayPal)
    location /api/ {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
"""
if "127.0.0.1:8010" in text:
    print("api location already present")
else:
    needle = "location / {"
    idx = text.find(needle)
    if idx == -1:
        raise SystemExit("could not find location / in nginx conf")
    text = text[:idx] + block + "\n" + text[idx:]
    p.write_text(text)
    print("inserted /api proxy")
PY
  nginx -t
  systemctl reload nginx
fi

# Spanish edition: /es/ pages are rendered by the app.
if [ -f "$CONF" ] && ! grep -q 'location /es/' "$CONF"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/etc/nginx/sites-enabled/thebookswanderer.com")
text = p.read_text()
proxy = """proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;"""
block = f"""
    # Spanish edition (server/i18n.py)
    location = /es {{
        {proxy}
    }}

    location /es/ {{
        {proxy}
    }}
"""
needle = "location / {"
idx = text.find(needle)
if idx == -1:
    raise SystemExit("could not find location / in nginx conf")
p.write_text(text[:idx] + block.lstrip("\n") + "\n    " + text[idx:])
print("inserted /es/ locations")
PY
  if nginx -t; then
    systemctl reload nginx
  else
    echo "nginx -t failed after adding /es/ — check $CONF"
  fi
fi

# Digital products: purchased files live outside the web root.
mkdir -p /var/lib/tbw-digital
chown www-data:www-data /var/lib/tbw-digital
chmod 750 /var/lib/tbw-digital

# Uploads of those files through /admin/digital/ need more than nginx's 1 MB default.
if [ -f "$CONF" ] && ! grep -q 'location /admin/digital/' "$CONF"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/etc/nginx/sites-enabled/thebookswanderer.com")
text = p.read_text()
block = """    # Digital product uploads (server/live.py)
    location /admin/digital/ {
        client_max_body_size 200m;
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_request_buffering off;
    }

    """
needle = "location / {"
idx = text.find(needle)
if idx == -1:
    raise SystemExit("could not find location / in nginx conf")
p.write_text(text[:idx] + block + text[idx:])
print("inserted /admin/digital/ location")
PY
  if nginx -t; then
    systemctl reload nginx
  else
    echo "nginx -t failed after adding /admin/digital/ — check $CONF"
  fi
fi

# Product image uploads use the same private administrator login.
if [ -f "$CONF" ] && ! grep -q 'location \^~ /admin/product-media/' "$CONF"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/etc/nginx/sites-enabled/thebookswanderer.com")
original = p.read_text()
block = """    location ^~ /admin/product-media/ {
        client_max_body_size 25m;
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

"""
needle = "location / {"
idx = original.find(needle)
if idx == -1:
    raise SystemExit("could not find nginx default location")
p.write_text(original[:idx] + block + original[idx:])
import subprocess
if subprocess.run(["nginx", "-t"]).returncode:
    p.write_text(original)
    raise SystemExit("invalid nginx product media configuration; original restored")
PY
  systemctl reload nginx
fi

# Daily product reel for Facebook + Instagram (server/scripts/daily_social_post.py).
# Cron fires at 15:03 and 16:03 UTC; --at-hour 11 keeps only the run that is
# 11:xx in New York, so the post holds its local time across DST.
if ! command -v ffmpeg >/dev/null 2>&1; then
  (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg >/dev/null) \
    || echo "WARNING: ffmpeg install failed; daily_social_post.py cannot render"
fi
touch /var/log/tbw-social.log
chown www-data:www-data /var/log/tbw-social.log
cat > /etc/cron.d/tbw-social-post <<CRON
3 15,16 * * * www-data cd $REMOTE_PATH/server && .venv/bin/python scripts/daily_social_post.py --at-hour 11 >> /var/log/tbw-social.log 2>&1
CRON
chmod 644 /etc/cron.d/tbw-social-post

# Supplier legs (CJ, Printify, Lulu, Prodigi): tracking email to the buyer when a leg
# ships, one inbox alert when a leg is stuck (server/scripts/sync_order_tracking.py).
rm -f /etc/cron.d/tbw-lulu-tracking
touch /var/log/tbw-tracking.log
chown www-data:www-data /var/log/tbw-tracking.log
cat > /etc/cron.d/tbw-order-tracking <<CRON
17 */2 * * * root /bin/systemctl start tbw-order-tracking.service >> /var/log/tbw-tracking.log 2>&1
CRON
chmod 644 /etc/cron.d/tbw-order-tracking

# Newsletter welcome series (server/scripts/send_welcome_series.py), hourly.
touch /var/log/tbw-welcome.log
chown www-data:www-data /var/log/tbw-welcome.log
cat > /etc/cron.d/tbw-welcome-series <<CRON
41 * * * * www-data cd $REMOTE_PATH/server && .venv/bin/python scripts/send_welcome_series.py >> /var/log/tbw-welcome.log 2>&1
CRON
chmod 644 /etc/cron.d/tbw-welcome-series

# Daily research no longer depends on GitHub's best-effort scheduled queue.
touch /var/log/tbw-reader-outreach.log /var/log/tbw-monthly.log
chown www-data:www-data /var/log/tbw-reader-outreach.log /var/log/tbw-monthly.log
cat > /etc/cron.d/tbw-reader-outreach <<CRON
15 12 * * * www-data cd $REMOTE_PATH/server && .venv/bin/python scripts/run_reader_outreach.py --send >> /var/log/tbw-reader-outreach.log 2>&1
CRON
chmod 644 /etc/cron.d/tbw-reader-outreach

# First issue: November 2026. The ledger allows safe catch-up on days 2 and 3.
cat > /etc/cron.d/tbw-monthly-newsletter <<CRON
35 12 1-3 * * www-data cd $REMOTE_PATH/server && .venv/bin/python scripts/send_monthly_newsletter.py --send >> /var/log/tbw-monthly.log 2>&1
CRON
chmod 644 /etc/cron.d/tbw-monthly-newsletter

# IndexNow (server/scripts/indexnow_submit.py): new / changed sitemap URLs to Bing & co, daily.
touch /var/log/tbw-indexnow.log
chown www-data:www-data /var/log/tbw-indexnow.log
cat > /etc/cron.d/tbw-indexnow <<CRON
17 7 * * * www-data cd $REMOTE_PATH/server && .venv/bin/python scripts/indexnow_submit.py >> /var/log/tbw-indexnow.log 2>&1
CRON
chmod 644 /etc/cron.d/tbw-indexnow

# One-time release tasks (server/scripts/release_queue.json), each run once as www-data;
# a failed task is retried on the next deploy.
cd "$REMOTE_PATH/server" && runuser -u www-data -- env PYTHONUNBUFFERED=1 .venv/bin/python scripts/run_release_queue.py || echo "WARNING: release queue failed"
# Every deploy: encrypted inbox for paid digital files (prints only the public key; see deploy/digital-inbox.py).
[ -f "$REMOTE_PATH/deploy/digital-inbox.py" ] && { python3 "$REMOTE_PATH/deploy/digital-inbox.py" "$REMOTE_PATH" || echo "WARNING: digital inbox failed"; }
# Every deploy: on-site copies of Printify mockups (their host blocks crawlers, so Merchant Center rejects them).
(cd "$REMOTE_PATH/server" && .venv/bin/python scripts/mirror_printify_images.py) || echo "WARNING: printify image mirror failed"

# One-time, root-only credential lookup by name (deploy/find-credential-names.sh never prints values).
mkdir -p /var/lib/tbw-once
if [ -f "$REMOTE_PATH/deploy/find-credential-names.sh" ] && [ ! -f /var/lib/tbw-once/find-bonanza ]; then
  bash "$REMOTE_PATH/deploy/find-credential-names.sh" bonanz || true
  touch /var/lib/tbw-once/find-bonanza
fi
if [ -f "$REMOTE_PATH/deploy/inspect-bonanza.sh" ] && [ ! -f /var/lib/tbw-once/inspect-bonanza ]; then
  bash "$REMOTE_PATH/deploy/inspect-bonanza.sh" || true
  touch /var/lib/tbw-once/inspect-bonanza
fi
if [ -f "$REMOTE_PATH/deploy/outline-bonanza.sh" ] && [ ! -f /var/lib/tbw-once/outline-bonanza ]; then
  bash "$REMOTE_PATH/deploy/outline-bonanza.sh" || true
  touch /var/lib/tbw-once/outline-bonanza
fi
if [ -f "$REMOTE_PATH/deploy/peek-bonanza-code.sh" ] && [ ! -f /var/lib/tbw-once/peek-bonanza-code ]; then
  bash "$REMOTE_PATH/deploy/peek-bonanza-code.sh" || true
  touch /var/lib/tbw-once/peek-bonanza-code
fi
if [ -f "$REMOTE_PATH/deploy/bonanza-read.sh" ] && [ ! -f /var/lib/tbw-once/bonanza-read ]; then
  bash "$REMOTE_PATH/deploy/bonanza-read.sh" || true
  touch /var/lib/tbw-once/bonanza-read
fi
if [ -f "$REMOTE_PATH/deploy/bonanza-read2.sh" ] && [ ! -f /var/lib/tbw-once/bonanza-read2 ]; then
  bash "$REMOTE_PATH/deploy/bonanza-read2.sh" || true
  touch /var/lib/tbw-once/bonanza-read2
fi
# One-time check of the Bonanza order worker (dry run while bonanza_skus.json has "live": false).
if [ ! -f /var/lib/tbw-once/bonanza-fulfill-check ]; then
  systemctl start tbw-order-tracking.service || true
  grep -n "Bonanza\|bonanza-" /var/log/tbw-tracking.log | tail -n 15 || true
  systemctl show -p Result --value tbw-order-tracking.service || true
  touch /var/lib/tbw-once/bonanza-fulfill-check
fi
# One-time: publish the three print-on-demand listings on the MathRelaxing Bonanza booth.
if [ -f "$REMOTE_PATH/deploy/bonanza-publish.py" ] && [ ! -f /var/lib/tbw-once/bonanza-publish ]; then
  touch /var/lib/tbw-once/bonanza-publish
  python3 "$REMOTE_PATH/deploy/bonanza-publish.py" || true
fi
# One-time, read-only: state of the Etsy -> Lulu worker for the 2026-11-02 puzzle-book order (no buyer data).
if [ -f "$REMOTE_PATH/deploy/inspect-etsy-lulu.py" ] && [ ! -f /var/lib/tbw-once/inspect-etsy-lulu ]; then
  touch /var/lib/tbw-once/inspect-etsy-lulu
  python3 "$REMOTE_PATH/deploy/inspect-etsy-lulu.py" || true
fi
if [ -f "$REMOTE_PATH/deploy/inspect-etsy-lulu2.py" ] && [ ! -f /var/lib/tbw-once/inspect-etsy-lulu2 ]; then
  touch /var/lib/tbw-once/inspect-etsy-lulu2
  python3 "$REMOTE_PATH/deploy/inspect-etsy-lulu2.py" || true
fi
if [ -f "$REMOTE_PATH/deploy/inspect-etsy-lulu3.py" ] && [ ! -f /var/lib/tbw-once/inspect-etsy-lulu3 ]; then
  touch /var/lib/tbw-once/inspect-etsy-lulu3
  python3 "$REMOTE_PATH/deploy/inspect-etsy-lulu3.py" || true
fi
# One-time: let the Etsy -> Lulu worker submit receipt 4220948340 again (job only; owner pays in Lulu).
if [ -f "$REMOTE_PATH/deploy/retry-etsy-lulu.py" ] && [ ! -f /var/lib/tbw-once/retry-etsy-lulu-4220948340-c ]; then
  touch /var/lib/tbw-once/retry-etsy-lulu-4220948340-c
  python3 "$REMOTE_PATH/deploy/retry-etsy-lulu.py" || true
fi
if [ -f "$REMOTE_PATH/deploy/inspect-etsy-lulu4.py" ] && [ ! -f /var/lib/tbw-once/inspect-etsy-lulu4 ]; then
  touch /var/lib/tbw-once/inspect-etsy-lulu4
  python3 "$REMOTE_PATH/deploy/inspect-etsy-lulu4.py" || true
fi
# One-time: Lulu needs pod_package_id inside printable_normalization; patch the Etsy -> Lulu worker,
# then resubmit receipt 4220948340 (job only; the owner pays in Lulu).
if [ -f "$REMOTE_PATH/deploy/fix-etsy-lulu-package.py" ] && [ ! -f /var/lib/tbw-once/fix-etsy-lulu-package ]; then
  touch /var/lib/tbw-once/fix-etsy-lulu-package
  if python3 "$REMOTE_PATH/deploy/fix-etsy-lulu-package.py" && [ ! -f /var/lib/tbw-once/retry-etsy-lulu-4220948340-d ]; then
    touch /var/lib/tbw-once/retry-etsy-lulu-4220948340-d
    python3 "$REMOTE_PATH/deploy/retry-etsy-lulu.py" || true
  fi
fi
# One-time, read-only: what fills the root disk (alert at 85% on 2026-11-03).
if [ -f "$REMOTE_PATH/deploy/disk-usage.sh" ] && [ ! -f /var/lib/tbw-once/disk-usage-20261103 ]; then
  touch /var/lib/tbw-once/disk-usage-20261103
  bash "$REMOTE_PATH/deploy/disk-usage.sh" || true
fi
# One-time disk cleanup approved by the owner (journal cap, old snaps, VS Code builds, caches).
if [ -f "$REMOTE_PATH/deploy/disk-cleanup.sh" ] && [ ! -f /var/lib/tbw-once/disk-cleanup-20261103 ]; then
  touch /var/lib/tbw-once/disk-cleanup-20261103
  bash "$REMOTE_PATH/deploy/disk-cleanup.sh" || true
fi
# One-time, read-only: which video projects match videos already public on YouTube.
if [ -f "$REMOTE_PATH/deploy/video-inventory.sh" ] && [ ! -f /var/lib/tbw-once/video-inventory-20261103 ]; then
  touch /var/lib/tbw-once/video-inventory-20261103
  bash "$REMOTE_PATH/deploy/video-inventory.sh" || true
fi
# One-time, owner-approved: delete the big video files of projects already public on YouTube.
if [ -f "$REMOTE_PATH/deploy/delete-published-videos.sh" ] && [ ! -f /var/lib/tbw-once/delete-published-videos-20261103 ]; then
  touch /var/lib/tbw-once/delete-published-videos-20261103
  bash "$REMOTE_PATH/deploy/delete-published-videos.sh" || true
fi
# One-time, read-only: Search Console report and installed MCP layout (before extending them).
if [ -f "$REMOTE_PATH/deploy/inspect-seo.sh" ] && [ ! -f /var/lib/tbw-once/inspect-seo-20261103 ]; then
  touch /var/lib/tbw-once/inspect-seo-20261103
  bash "$REMOTE_PATH/deploy/inspect-seo.sh" || true
fi
# One-time, read-only: installed MCP and Search Console report code (secrets masked).
if [ -f "$REMOTE_PATH/deploy/show-seo-code.sh" ] && [ ! -f /var/lib/tbw-once/show-seo-code-20261103 ]; then
  touch /var/lib/tbw-once/show-seo-code-20261103
  bash "$REMOTE_PATH/deploy/show-seo-code.sh" || true
fi
# One-time: local read-only Search Console query service and two MCP tools (with backup/rollback).
if [ -f "$REMOTE_PATH/deploy/seo_query_install.py" ] && [ ! -f /var/lib/tbw-once/seo-query-install-20261103 ]; then
  touch /var/lib/tbw-once/seo-query-install-20261103
  python3 "$REMOTE_PATH/deploy/seo_query_install.py" || echo "WARNING: seo-query install incomplete"
fi
# One-time, read-only: test the Search Console query service.
if [ -f "$REMOTE_PATH/deploy/seo-query-test.py" ] && [ ! -f /var/lib/tbw-once/seo-query-test-20261103 ]; then
  touch /var/lib/tbw-once/seo-query-test-20261103
  python3 "$REMOTE_PATH/deploy/seo-query-test.py" || true
fi
# One-time, owner-requested: disable the autonomous editorial pilot and report what it did.
if [ -f "$REMOTE_PATH/deploy/disable-seo-editor.sh" ] && [ ! -f /var/lib/tbw-once/disable-seo-editor-20261103 ]; then
  touch /var/lib/tbw-once/disable-seo-editor-20261103
  bash "$REMOTE_PATH/deploy/disable-seo-editor.sh" || true
fi
# One-time, read-only: Search Console exploration for new content ideas.
if [ -f "$REMOTE_PATH/deploy/seo-explore.py" ] && [ ! -f /var/lib/tbw-once/seo-explore-20261103 ]; then
  touch /var/lib/tbw-once/seo-explore-20261103
  python3 "$REMOTE_PATH/deploy/seo-explore.py" || true
fi
# One-time, owner-approved: Meta ads through the store, paused only, with a daily budget cap.
if [ -f "$REMOTE_PATH/deploy/enable-meta-ads-paused.sh" ] && [ ! -f /var/lib/tbw-once/enable-meta-ads-paused-20261103 ]; then
  touch /var/lib/tbw-once/enable-meta-ads-paused-20261103
  bash "$REMOTE_PATH/deploy/enable-meta-ads-paused.sh" || true
fi
# One-time, read-only: Etsy auth diagnosis.
if [ -f "$REMOTE_PATH/deploy/inspect-etsy-auth.sh" ] && [ ! -f /var/lib/tbw-once/inspect-etsy-auth-20261103 ]; then
  touch /var/lib/tbw-once/inspect-etsy-auth-20261103
  bash "$REMOTE_PATH/deploy/inspect-etsy-auth.sh" || true
fi
# One-time, read-only: where the site visits come from.
if [ -f "$REMOTE_PATH/deploy/visits-report.sh" ] && [ ! -f /var/lib/tbw-once/visits-report-20261107 ]; then
  touch /var/lib/tbw-once/visits-report-20261107
  bash "$REMOTE_PATH/deploy/visits-report.sh" || true
fi
