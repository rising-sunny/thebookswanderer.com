"""Read exact CJ variants and report identifier evidence; never change catalog.

Uses the inherited CJ_API_KEY through the normal CJ client. Does not print
credentials, create orders, import products, or treat supplier SKUs as MPNs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import cj

PRODUCTS = {
    "reading-log-bookmarks": "CJYD207807803CX",
    "baker-street-book-nook-kit": "CJYZ30260030001",
}
IDENTIFIER_KEYS = {
    "brand", "brandname", "brandnameen", "manufacturer", "manufacturername",
    "manufacturerpartnumber", "mpn", "gtin", "gtin8", "gtin12", "gtin13",
    "gtin14", "upc", "ean", "barcode", "isbn", "model", "modelnumber",
    "productkey", "productkeyen", "productproperty", "productpropertylist",
    "productbrand", "productbarcode", "productgtin", "productmpn",
    "variantbrand", "variantbarcode", "variantgtin", "variantmpn",
}


def evidence(data, path=""):
    fields = []
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = "".join(c for c in key.lower() if c.isalnum())
            current = f"{path}.{key}" if path else key
            if normalized in IDENTIFIER_KEYS and value not in (None, "", [], {}):
                fields.append({"path": current, "value": value})
            elif isinstance(value, (dict, list)):
                fields.extend(evidence(value, current))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            fields.extend(evidence(value, f"{path}[{i}]"))
    return fields


async def audit(slugs):
    if not cj.is_configured():
        raise SystemExit("CJ_API_KEY is not configured in this environment.")
    for slug in slugs:
        sku = PRODUCTS[slug]
        try:
            product = await cj.get_product_details(variant_sku=sku)
            variants = [v for v in product.get("variants") or []
                        if str(v.get("variantSku") or "") == sku]
            filtered = {k: v for k, v in product.items() if k != "variants"}
            result = {
                "slug": slug, "requested_variant_sku": sku,
                "product_name": product.get("productNameEn"),
                "product_sku": product.get("productSku"),
                "variant_match": bool(variants),
                "product_identifier_fields": evidence(filtered),
                "variant_identifier_fields": [evidence(v) for v in variants],
                "top_level_fields": sorted(product),
            }
            print(json.dumps(result, ensure_ascii=False))
        except cj.CJError as exc:
            # Only the non-secret API code; avoid dumping auth-response bodies.
            code = exc.payload.get("code") if isinstance(exc.payload, dict) else None
            print(json.dumps({"slug": slug, "error": "CJ request failed", "code": code}))
        await asyncio.sleep(1.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", action="append", choices=sorted(PRODUCTS))
    args = parser.parse_args()
    asyncio.run(audit(args.slug or list(PRODUCTS)))
