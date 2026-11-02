#!/bin/bash
# One-time, read-only: the exact shape Bonanza accepted before, so new listings copy it.
#  1) variations / shipping / specifics / return policy of live booth items (via the gateway)
#  2) the function in the earlier publishing scripts that builds an addFixedPriceItem payload
#     (string literals that look like keys are redacted; credentials are not in these scripts)
set -u
python3 - <<'PY'
import json, socket
SOCK = "/run/mathrelaxing-bonanza-api/api.sock"
def call(endpoint, payload):
    msg = {"action": "request", "method": "POST", "endpoint": endpoint, "payload": payload}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.settimeout(90); c.connect(SOCK); c.sendall(json.dumps(msg).encode() + b"\n")
        with c.makefile("rb") as s:
            return json.loads(s.readline(8 * 1024 * 1024 + 1))
r = call("/getBoothItemsRequest", {"userId": "mathrelaxing", "itemsPerPage": 50, "page": 1})
items = (r.get("data") or {}).get("getBoothItemsResponse", {}).get("items") or []
shown = 0
for it in items:
    if not it.get("variations") and shown:
        continue
    print(f"== item {it.get('itemID')} {str(it.get('title'))[:60]} | cat {(it.get('primaryCategory') or {}).get('categoryId')}")
    for k in ("variations", "shippingCostSummary", "itemSpecifics", "returnPolicy", "paymentMethods", "shipToLocations", "listingType", "sku", "quantity", "pictureURL"):
        v = json.dumps(it.get(k), ensure_ascii=False)
        print(f"  {k}: {v[:900]}{' ...' if len(v) > 900 else ''}")
    shown += 1
    if shown >= 2:
        break
PY
python3 - <<'PY'
import ast, re, glob
TOKENISH = re.compile(r"(['\"])([A-Za-z0-9_\-+/=.]{24,})\1")
files = sorted(glob.glob("/root/bonanza-products-*.py") + glob.glob("/root/bonanza-printify-*.py")
               + glob.glob("/root/marketplace-api-review.*/push_bonanza.py"))
for path in files:
    src = open(path, errors="replace").read()
    if "addFixedPriceItem" not in src:
        continue
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    lines = src.splitlines()
    print(f"== {path}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = "\n".join(lines[node.lineno - 1:node.end_lineno])
            if re.search(r"item|payload|listing|variation|shipping", node.name, re.I) and len(seg) < 6000:
                print(f"-- {node.name}")
                print(TOKENISH.sub(lambda m: m.group(1) + "<redacted>" + m.group(1), seg))
    break
PY
echo "== done"
