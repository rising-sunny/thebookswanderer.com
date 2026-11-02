#!/usr/bin/env python3
"""One-time: publish the listings in deploy/bonanza-listings.json on the MathRelaxing Bonanza booth
through the existing gateway (credentials stay there). Each attempt carries an idempotency key, so a
rerun never lists twice. If Bonanza rejects a category, the next candidate is tried; a rejection
publishes nothing. Afterwards the booth is read back to report the new item ids and categories.
"""
import json
import socket
import sys
from pathlib import Path

SOCK = "/run/mathrelaxing-bonanza-api/api.sock"
LISTINGS = Path(__file__).with_name("bonanza-listings.json")
# Bonanza uses eBay's category ids (its mug category is eBay's 20695). None = let Bonanza choose.
CATEGORIES = {"TBW-ORN-SET": [117414, 38227, None], "TBW-PP-SWEAT": [155183, 155226, None], "TBW-PP-MUG": [20695]}
INTERNATIONAL = {"TBW-ORN-SET": 14.99, "TBW-PP-SWEAT": 14.99, "TBW-PP-MUG": 12.99}


def call(endpoint, payload, key=""):
    msg = {"action": "request", "method": "POST", "endpoint": endpoint, "payload": payload}
    if key:
        msg["idempotency_key"] = key
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.settimeout(90); c.connect(SOCK); c.sendall(json.dumps(msg).encode() + b"\n")
        with c.makefile("rb") as s:
            return json.loads(s.readline(8 * 1024 * 1024 + 1))


def item_payload(it, category):
    specifics = [["Condition", "New"], ["Brand", "MathRelaxing"]] + [[k, str(v)] for k, v in it.get("itemSpecifics", {}).items()]
    item = {
        "title": it["title"], "description": it["description"], "sku": it["sku"],
        "price": f"{it['price']:.2f}", "quantity": it.get("quantity", 99),
        "itemSpecifics": specifics,
        "pictureDetails": {"pictureURL": it["pictureURLs"]},
        "shippingDetails": {
            "shippingServiceOptions": [{"freeShipping": True}],
            "internationalShippingServiceOption": [{"shippingServiceCost": f"{INTERNATIONAL[it['sku']]:.2f}", "shipToLocation": "Worldwide"}],
        },
    }
    if category:
        item["primaryCategory"] = {"categoryId": category}
    if it.get("variations"):
        item["variations"] = [{"sku": v["sku"], "quantity": 25, "price": f"{v['price']:.2f}",
                               "nameValueList": v["nameValueList"]} for v in it["variations"]]
        item["quantity"] = sum(v["quantity"] for v in item["variations"])
    return {"item": item}


def main():
    listings = json.loads(LISTINGS.read_text())["items"]
    for it in listings:
        sku = it["sku"]
        for n, category in enumerate(CATEGORIES[sku]):
            r = call("/addFixedPriceItemRequest", item_payload(it, category), key=f"tbw-publish-{sku}-c{n}")
            data = r.get("data") or {}
            text = json.dumps(data)[:600]
            if r.get("status") == 200:
                resp = data.get("addFixedPriceItemResponse", data)
                print(f"{sku}: listed, item {resp.get('itemId')}, category {resp.get('categoryId', category)}, state {resp.get('sellingState')}")
                break
            print(f"{sku}: category {category} rejected: {r.get('status')} {text}")
            if "categor" not in text.lower():
                print(f"{sku}: stopped (not a category problem)")
                break
    r = call("/getBoothItemsRequest", {"userId": "mathrelaxing", "itemsPerPage": 50, "page": 1})
    items = ((r.get("data") or {}).get("getBoothItemsResponse") or {}).get("items") or []
    print(f"booth now has {len(items)} items")
    for i in items:
        if str(i.get("sku", "")).startswith("TBW-"):
            cat = i.get("primaryCategory") or {}
            print(f"  {i.get('itemID')} {i.get('sku')} {i.get('currentPrice')} | {cat.get('categoryId')} {cat.get('categoryName')} | {i.get('viewItemURL')}")


if __name__ == "__main__":
    sys.exit(main())
