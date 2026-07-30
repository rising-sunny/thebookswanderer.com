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
