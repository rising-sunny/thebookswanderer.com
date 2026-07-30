import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sku = sys.argv[1] if len(sys.argv) > 1 else "CJJT1576683"
key = os.environ.get("CJ_API_KEY", "")
if not key:
    raise SystemExit("CJ_API_KEY required")

req = urllib.request.Request(
    "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken",
    data=json.dumps({"apiKey": key}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=40) as r:
    tok = json.loads(r.read().decode())["data"]["accessToken"]

req2 = urllib.request.Request(
    f"https://developers.cjdropshipping.com/api2.0/v1/product/query?productSku={sku}",
    headers={"CJ-Access-Token": tok},
)
with urllib.request.urlopen(req2, timeout=45) as r2:
    d = json.loads(r2.read().decode())["data"]

out = Path(__file__).resolve().parents[1] / "data" / f"{sku}.json"
out.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
print("name", d.get("productNameEn"))
print("price", d.get("sellPrice"))
print("pid", d.get("pid"))
print("cat", d.get("categoryName"))
vs = d.get("variants") or []
print("n variants", len(vs))
for v in vs:
    print("-", v.get("variantKey"), v.get("variantSellPrice"), (v.get("variantImage") or "")[-60:])
print("big", d.get("bigImage"))
print("set count", len(d.get("productImageSet") or []))
for u in d.get("productImageSet") or []:
    print(" set", u)
desc_imgs = re.findall(r'src="(https://[^"]+)"', d.get("description") or "")
print("desc imgs", len(desc_imgs))
for u in desc_imgs:
    print(" desc", u)
print("saved", out)
