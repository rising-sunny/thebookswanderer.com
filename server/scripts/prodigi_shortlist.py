"""Compare researched Home Decor SKUs, one unit/order each; never creates orders."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.prodigi import Client, ProdigiError

CANDIDATES = [
    ("Matte art print 11x14", "GLOBAL-FAP-11X14"),
    ("Matte art print 12x16", "GLOBAL-FAP-12X16"),
    ("Classic framed print 11x14", "GLOBAL-CFP-11X14"),
    ("Cushion cover only 18x18", "H-CUSHCOV-18X18"),
    ("Printed wall tapestry 26x36", "GLOBAL-TAP-XS"),
    ("Woven wall hanging 27x37, rod not included", "GLOBAL-TAP-WOV-27X37"),
]


def quote_item(product):
    variants = [v for v in product.get("variants", [])
                if isinstance(v, dict) and "US" in v.get("shipsTo", [])]
    if not variants:
        raise ProdigiError("No variant available for US delivery")
    # Prefer black if offered; expose exact choice rather than assuming attributes.
    variant = next((v for v in variants
                    if v.get("attributes", {}).get("color", "").lower() == "black"),
                   variants[0])
    areas = product.get("printAreas", {})
    if not isinstance(areas, dict):
        raise ProdigiError("Invalid print-area data")
    assets = [{"printArea": name} for name, area in areas.items()
              if isinstance(area, dict) and area.get("required") is True]
    if not assets:
        raise ProdigiError("No required print areas; review manually before quoting")
    if variant.get("pagePricing"):
        raise ProdigiError("Page count required; review manually before quoting")
    return {"sku": product["sku"], "copies": 1,
            "attributes": variant.get("attributes", {}), "assets": assets}


async def inspect(client, name, sku):
    record = {"name": name, "sku": sku}
    try:
        product = (await client.product_details(sku))["product"]
        item = quote_item(product)
        result = await client.quote_us([item])
        options = []
        for quote in result["quotes"]:
            locations = sorted({s.get("fulfillmentLocation", {}).get("countryCode", "unknown")
                                for s in quote.get("shipments", [])})
            options.append({
                "shipping_method": quote.get("shipmentMethod"),
                "costs": quote["costSummary"],
                "fulfillment_countries": locations,
            })
        record.update({"description": product.get("description"),
                       "dimensions": product.get("productDimensions"),
                       "selected_variant": item["attributes"],
                       "print_areas": item["assets"],
                       "quote_outcome": result.get("outcome"),
                       "issues": result.get("issues", []), "quotes": options})
    except ProdigiError as error:
        record["error"] = str(error)
    return record


async def main():
    async with Client.from_env() as client:
        records = []
        for name, sku in CANDIDATES:
            print("Checking " + sku, file=sys.stderr, flush=True)
            records.append(await inspect(client, name, sku))
    print(json.dumps({"environment": "live", "destination": "US", "currency": "USD",
                      "basis": "one unit quoted separately per SKU; tax may be excluded",
                      "order_submission_enabled": False,
                      "product_publication_enabled": False,
                      "candidates": records}, indent=2))
    return 1 if any("error" in r for r in records) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except ProdigiError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
