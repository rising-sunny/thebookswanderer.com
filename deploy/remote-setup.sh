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
chmod 640 "$REMOTE_PATH/server/.env" || true
chmod 755 "$REMOTE_PATH/server/data"
# www-data needs write for sqlite
chown www-data:www-data "$REMOTE_PATH/server/data"

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
