"""Fetch one CJ product by SPU/SKU and print a summary."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

KEY = __import__("os").environ.get("CJ_API_KEY", "")
SKU = sys.argv[1] if len(sys.argv) > 1 else "CJYD2138789"
if not KEY:
    raise SystemExit("Set CJ_API_KEY env var")


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"CJ-Access-Token": token})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def main() -> None:
    auth = post_json(
        "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken",
        {"apiKey": KEY},
    )
    token = (auth.get("data") or {}).get("accessToken")
    if not token:
        print(json.dumps(auth, indent=2))
        raise SystemExit("no token")

    body = get_json(
        f"https://developers.cjdropshipping.com/api2.0/v1/product/query?productSku={SKU}",
        token,
    )
    print("code", body.get("code"), body.get("message"))
    d = body.get("data") or {}
    if not d:
        print(json.dumps(body, indent=2)[:3000])
        raise SystemExit(1)

    print("pid", d.get("pid"))
    print("name", d.get("productNameEn"))
    print("sku", d.get("productSku"))
    print("image", (d.get("bigImage") or "")[:100])
    print("sellPrice", d.get("sellPrice"))
    print("category", d.get("categoryName"))
    variants = d.get("variants") or []
    print("variants", len(variants))
    for v in variants:
        inv = v.get("inventories") or []
        countries = ",".join(i.get("countryCode", "") for i in inv[:6])
        print(
            f"  vid={v.get('vid')} sku={v.get('variantSku')} "
            f"price={v.get('variantSellPrice')} key={v.get('variantKey')} inv={countries}"
        )

    out = Path(__file__).resolve().parents[1] / "data" / f"{SKU}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
