#!/bin/bash
set -e
PASS=$(grep '^LIVE_ADMIN_PASSWORD=' /var/www/thebookswanderer.com/server/.env | cut -d= -f2-)
echo "pass_set=$([ -n "$PASS" ] && echo yes || echo no)"
curl -s -o /dev/null -w "login:%{http_code}\n" https://thebookswanderer.com/admin/live/login
curl -s -o /dev/null -w "admin:%{http_code}\n" https://thebookswanderer.com/admin/live
curl -s -o /dev/null -w "track:%{http_code}\n" -X POST https://thebookswanderer.com/api/track \
  -H 'Content-Type: application/json' \
  -d '{"type":"pageview","session_id":"testsession01","path":"/"}'
rm -f /tmp/tbw_cj
curl -s -c /tmp/tbw_cj -b /tmp/tbw_cj -o /dev/null -w "loginpage:%{http_code}\n" \
  https://thebookswanderer.com/admin/live/login
curl -s -c /tmp/tbw_cj -b /tmp/tbw_cj -o /dev/null -w "loginpost:%{http_code}\n" \
  -X POST https://thebookswanderer.com/admin/live/login \
  --data-urlencode "username=tbw" \
  --data-urlencode "password=${PASS}"
curl -s -c /tmp/tbw_cj -b /tmp/tbw_cj -o /dev/null -w "dash:%{http_code}\n" \
  https://thebookswanderer.com/admin/live
echo -n "snapshot:"
curl -s -c /tmp/tbw_cj -b /tmp/tbw_cj https://thebookswanderer.com/admin/live/snapshot | head -c 500
echo
journalctl -u thebookswanderer -n 25 --no-pager
