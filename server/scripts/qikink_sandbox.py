#!/usr/bin/env python3
"""Sandbox-only Qikink CLI. Plain orders default to a dry run."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from services.qikink import PlainOrder, QikinkError, SandboxClient, SandboxJournal, DEFAULT_JOURNAL


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
    lookup = commands.add_parser("lookup", help="Read only; unavailable Sandbox routes are reported")
    lookup.add_argument("order_id")
    history = commands.add_parser("status", help="Read the local journal, with no network call")
    history.add_argument("reference")
    for name in ("plain", "remember"):
        sub = commands.add_parser(name)
        sub.add_argument("--reference", required=True, help="Reuse the same reference for the same logical order")
        sub.add_argument("--sku", default="MVnHs-Wh-S")
        if name == "plain":
            sub.add_argument("--submit-sandbox", action="store_true", help="Actually create one plain Sandbox order")
        else:
            sub.add_argument("--order-id", required=True, help="Manually confirmed ID of an existing plain Sandbox test")
    return cli


async def run(args) -> dict:
    order = None
    if args.command in {"plain", "remember"}:
        order = PlainOrder(reference=args.reference, sku=args.sku, shipping_address=TEST_ADDRESS)
        if args.command == "plain" and not args.submit_sandbox:
            return {"environment": "sandbox", "dry_run": True, "payload": order.payload()}
    journal = SandboxJournal(args.journal)
    async with SandboxClient.from_env(journal) as client:
        if args.command == "auth":
            await client.authenticate()
            return {"environment": "sandbox", "authenticated": True}
        if args.command == "plain":
            return {"environment": "sandbox", **await client.create_plain_order(order)}
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
