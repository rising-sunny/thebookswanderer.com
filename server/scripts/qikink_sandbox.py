#!/usr/bin/env python3
"""Sandbox-only Qikink CLI. Plain and DTG printed orders default to a dry run."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from services.qikink import PlainOrder, PrintedOrder, PrintDesign, QikinkError, SandboxClient, SandboxJournal, DEFAULT_JOURNAL
from services.qikink_catalog import DEFAULT_CATALOG, DEFAULT_STORE_DB, load_catalog, catalog_report


# Matches the synthetic address of the manually confirmed Sandbox order.
TEST_ADDRESS = {
    "first_name": "Sandbox", "last_name": "Test", "address1": "Sandbox test address",
    "phone": "9876543210", "email": "sandbox@example.com", "city": "Coimbatore",
    "zip": "641001", "province": "Tamil Nadu", "country_code": "IN",
}


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("auth", help="Authenticate only; prints no token")
    catalog = commands.add_parser("catalog", help="Offline draft mapping/cost report; never publishes products")
    catalog.add_argument("--file", type=Path, default=DEFAULT_CATALOG)
    catalog.add_argument("--store-db", type=Path, default=DEFAULT_STORE_DB)
    catalog.add_argument("--country", action="append", help="Requested ISO country, e.g. US; repeat as needed")
    lookup = commands.add_parser("lookup", help="Read only; unavailable Sandbox routes are reported")
    lookup.add_argument("order_id")
    history = commands.add_parser("status", help="Read the local journal, with no network call")
    history.add_argument("reference")
    for name in ("plain", "printed", "remember"):
        sub = commands.add_parser(name)
        sub.add_argument("--reference", required=True, help="Reuse the same reference for the same logical order")
        sub.add_argument("--sku", default="MVnHs-Wh-S")
        if name in {"plain", "printed"}:
            sub.add_argument("--submit-sandbox", action="store_true", help="Actually create one Sandbox order")
        else:
            sub.add_argument("--order-id", required=True, help="Manually confirmed ID of an existing plain Sandbox test")
        if name == "printed":
            sub.add_argument("--design-code", help="Defaults to reference + _d; reuse the same code for the same artwork")
            sub.add_argument("--design-url", default="https://thebookswanderer.com/assets/logo.png")
            sub.add_argument("--mockup-url", default="https://thebookswanderer.com/assets/logo.png",
                             help="Sandbox placeholder by default; not a product mockup for sale")
            sub.add_argument("--width", type=float, default=2)
            sub.add_argument("--height", type=float, default=2)
    return cli


async def run(args) -> dict:
    if args.command == "catalog":
        catalog = load_catalog(args.file)
        if args.country is not None:
            catalog = type(catalog).model_validate(catalog.model_dump() | {"requested_countries": args.country})
        return catalog_report(catalog, args.store_db)
    order = None
    if args.command in {"plain", "printed", "remember"}:
        values = dict(reference=args.reference, sku=args.sku, shipping_address=TEST_ADDRESS)
        if args.command == "printed":
            order = PrintedOrder(**values, design=PrintDesign(
                design_code=args.design_code or args.reference + "_d", width_inches=args.width, height_inches=args.height,
                design_link=args.design_url, mockup_link=args.mockup_url))
        else:
            order = PlainOrder(**values)
        if args.command in {"plain", "printed"} and not args.submit_sandbox:
            return {"environment": "sandbox", "dry_run": True, "payload": order.payload()}
    journal = SandboxJournal(args.journal)
    async with SandboxClient.from_env(journal) as client:
        if args.command == "auth":
            await client.authenticate()
            return {"environment": "sandbox", "authenticated": True}
        if args.command == "plain":
            return {"environment": "sandbox", **await client.create_plain_order(order)}
        if args.command == "printed":
            return {"environment": "sandbox", **await client.create_printed_order(order)}
        if args.command == "remember":
            return {"environment": "sandbox", "source": "operator_confirmed",
                    "reference": order.reference, **client.remember_existing(order, args.order_id)}
        if args.command == "status":
            return {"environment": "sandbox", "record": journal.get(client.account, args.reference)}
        return {"environment": "sandbox", **await client.lookup(args.order_id)}


def main() -> int:
    args = parser().parse_args()
    load_dotenv(ROOT / ".env")
    try:
        result = asyncio.run(run(args))
    except QikinkError as exc:
        print(json.dumps({"environment": "sandbox", "error": str(exc), "error_type": type(exc).__name__}))
        return 1
    except (Exception, KeyboardInterrupt) as exc:
        # Validation errors, transport URLs, and SQLite messages can expose data.
        print(json.dumps({"environment": "sandbox", "error_type": type(exc).__name__,
                          "detail": "Check failed; details withheld. Inspect the journal before retrying submission."}))
        return 1
    print(json.dumps(result, indent=2))
    return 2 if result.get("state") == "unverified" else 0


if __name__ == "__main__":
    sys.exit(main())
