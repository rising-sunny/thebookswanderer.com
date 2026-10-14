"""Verified product identifiers shared by the public API, JSON-LD and feeds.

Supplier inventory SKUs are never promoted to manufacturer identifiers. A
product-level GTIN/MPN is used only for a product with at most one variant.
"""
from __future__ import annotations

from collections.abc import Mapping


def valid_gtin(value: object) -> str:
    code = str(value or "").strip()
    if len(code) not in (8, 12, 13, 14) or not code.isascii() or not code.isdigit():
        return ""
    if len(set(code)) == 1:
        return ""
    total = sum(int(n) * (3 if i % 2 == 0 else 1)
                for i, n in enumerate(reversed(code[:-1])))
    return code if (10 - total % 10) % 10 == int(code[-1]) else ""


def for_product(product: Mapping, variant: Mapping | None = None) -> dict[str, str]:
    result = {}
    brand = str(product.get("brand") or "").strip()
    if brand:
        result["brand"] = brand
    # Different options can have different manufacturer codes. Do not assign
    # a family-level identifier to all variants or to an unselected PDP.
    variants = product.get("variants") or []
    base = product if len(variants) <= 1 else {}
    if variant is None and len(variants) == 1:
        variant = variants[0]
    for key in ("mpn", "gtin"):
        value = str((variant or {}).get(key) or base.get(key) or "").strip()
        if key == "gtin":
            value = valid_gtin(value)
        if value:
            result[key] = value
    return result


# The calendar is designed in this repository and published to the owner's
# Printify shop by scripts/import_printify_products.py. Matching both provider
# and product id prevents a different item with the same slug inheriting it.
OWN_CALENDAR = {
    "slug": "readers-2027-desk-calendar",
    "supplier": "printify",
    "printify_product_id": "6acaf5de8ed76a615a0adea3",
    "brand": "The Books Wanderer",
    # Manufacturer reference assigned here to the shop's own calendar design.
    # This is not a GTIN and is not derived from a supplier's inventory SKU.
    "mpn": "TBW-READERS-2027",
}
