"""Product lookup or US quote; never creates orders or modifies the store."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.prodigi import Client, ProdigiError


async def run(args):
    async with Client.from_env() as client:
        if args.product:
            data = await client.product_details(args.product)
        else:
            try:
                items = json.loads(Path(args.quote_items).read_text())
            except (OSError, ValueError):
                raise ProdigiError("Cannot read quote items JSON") from None
            data = await client.quote_us(items)
    print(json.dumps({
        "environment": "live", "order_submission_enabled": False,
        "product_publication_enabled": False, "result": data,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--product", metavar="SKU")
    operation.add_argument("--quote-items", metavar="JSON_FILE")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except ProdigiError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
