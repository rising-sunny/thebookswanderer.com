#!/bin/bash
# One-time, read-only: ask the existing Bonanza gateway (local socket) about the booth, to learn
# the booth id, the categories its items use and the shape of a live listing. No writes.
set -u
python3 - <<'PY'
import json, socket

SOCK = "/run/mathrelaxing-bonanza-api/api.sock"

def call(endpoint, payload=None):
    msg = {"action": "request", "method": "POST", "endpoint": endpoint, "payload": payload or {}}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.settimeout(90); c.connect(SOCK); c.sendall(json.dumps(msg).encode() + b"\n")
        with c.makefile("rb") as s:
            return json.loads(s.readline(8 * 1024 * 1024 + 1))

def show(label, value, limit=2500):
    text = json.dumps(value, ensure_ascii=False)
    print(f"-- {label}: {text[:limit]}{' ...' if len(text) > limit else ''}")

def find(obj, keys):
    """first value for any of keys, searching nested dicts/lists"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, (str, int)):
                return v
        for v in obj.values():
            r = find(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, keys)
            if r is not None:
                return r
    return None

tok = call("/getTokenStatusRequest")
print("token status:", tok.get("status"), json.dumps(tok.get("data"), ensure_ascii=False)[:600])
user = find(tok.get("data"), {"userId", "userID", "username", "userName", "boothId"})
candidates = [u for u in [user, "mathrelaxing", "MathRelaxing"] if u]
items_resp = None
for uid in candidates:
    r = call("/getBoothItemsRequest", {"userId": uid, "itemsPerPage": 50, "page": 1})
    print(f"booth items for {uid!r}: status {r.get('status')}")
    if r.get("status") == 200:
        items_resp = r["data"]; break
    show("error", r.get("data"), 600)
if items_resp:
    def items_of(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k.lower() in ("items", "item") and isinstance(v, list):
                    return v
                r = items_of(v)
                if r:
                    return r
        return []
    items = items_of(items_resp)
    print(f"items returned: {len(items)}")
    cats = {}
    for it in items:
        cat = it.get("primaryCategory") or {}
        cid = cat.get("categoryId") or cat.get("categoryID") or it.get("categoryId")
        cname = cat.get("categoryName") or ""
        cats.setdefault((cid, cname), []).append(str(it.get("title", ""))[:70])
    print("categories in use:")
    for (cid, cname), titles in sorted(cats.items(), key=lambda x: -len(x[1])):
        print(f"  {cid} {cname}: {len(titles)} items, e.g. {titles[:2]}")
    if items:
        show("keys of one item", sorted(items[0].keys()))
        show("one item (as Bonanza returns it)", items[0], 4000)
    show("response top level", {k: (v if not isinstance(v, (dict, list)) else type(v).__name__) for k, v in items_resp.items()} if isinstance(items_resp, dict) else items_resp, 800)
PY
echo "== done"
