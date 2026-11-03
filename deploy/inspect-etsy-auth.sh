#!/bin/bash
# One-time, read-only: why Etsy calls fail from the store (owner request 2026-11-03).
# Prints presence/booleans, token age and HTTP status codes only; never a key or token value.
R=/var/www/thebookswanderer.com/server
echo "== env names (set/empty)"
for k in ETSY_API_KEY ETSY_TOKEN_FILE ETSY_SHOP_ID; do
  v=$(grep -E "^$k=" "$R/.env" 2>/dev/null | head -1 | cut -d= -f2-)
  echo "  $k: $([ -n "$v" ] && echo set || echo empty)"
done
cd "$R" && runuser -u www-data -- .venv/bin/python - <<'PY'
import asyncio, json, os, time
from dotenv import load_dotenv
load_dotenv(".env")
from services import etsy
import httpx
p = etsy.token_file()
print("== token file:", "exists" if p.exists() else "missing", "| writable dir:", os.access(p.parent, os.W_OK))
try:
    t = json.loads(p.read_text())
    print("   keys:", sorted(t), "| expires in (min):", round((int(t.get("expires_at", 0)) - time.time()) / 60))
except Exception as e:
    print("   unreadable:", type(e).__name__)
async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(etsy.BASE + "/application/openapi-ping", headers={"x-api-key": etsy.api_key()})
        print("== ping (api key only):", r.status_code, r.text[:200])
        try:
            tok = await etsy.access_token(c)
            print("== access token: ok")
        except Exception as e:
            print("== access token failed:", type(e).__name__, str(e)[:200]); return
        r = await c.get(etsy.BASE + "/application/users/me", headers={"x-api-key": etsy.api_key(), "Authorization": "Bearer " + tok})
        print("== users/me:", r.status_code, r.text[:300] if r.status_code != 200 else "ok (shop_id present: %s)" % ("shop_id" in r.text))
asyncio.run(main())
PY
echo "== recent store log lines mentioning etsy (last 15)"
journalctl -u thebookswanderer.service --since "-2 days" --no-pager -o cat 2>/dev/null | grep -i etsy | sed -E 's/([A-Za-z0-9_+\/=-]{32,})/<redacted>/g' | tail -15
echo "== admin-api routes mentioning etsy"
grep -n "etsy" /opt/tbw-admin-api/app.py 2>/dev/null | head -10
echo "== done"
