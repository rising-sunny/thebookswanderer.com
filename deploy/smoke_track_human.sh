#!/bin/bash
set -e
curl -s -X POST https://thebookswanderer.com/api/track \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' \
  -d '{"type":"pageview","session_id":"humansession99","path":"/","source":"direct"}'
echo
PASS=$(grep '^LIVE_ADMIN_PASSWORD=' /var/www/thebookswanderer.com/server/.env | cut -d= -f2-)
rm -f /tmp/tbw_cj2
curl -s -c /tmp/tbw_cj2 -b /tmp/tbw_cj2 -X POST https://thebookswanderer.com/admin/live/login \
  --data-urlencode "username=tbw" \
  --data-urlencode "password=${PASS}" -o /dev/null
curl -s -c /tmp/tbw_cj2 -b /tmp/tbw_cj2 https://thebookswanderer.com/admin/live/snapshot
echo
