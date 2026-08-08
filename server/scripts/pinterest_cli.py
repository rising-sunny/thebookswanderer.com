#!/usr/bin/env python3
"""CLI for The Books Wanderer Pinterest (own app + OAuth token).

Usage (from server/ with venv + .env):

  python scripts/pinterest_cli.py whoami
  python scripts/pinterest_cli.py boards
  python scripts/pinterest_cli.py create-board "Book accessories" --description "..."
  python scripts/pinterest_cli.py pin-product hollow-kitten-bookmark --board-id <ID>
  python scripts/pinterest_cli.py oauth-url   # print authorize URL (needs admin flow or use browser)

OAuth (browser, logged into TBW Pinterest account):
  https://thebookswanderer.com/api/pinterest/oauth/start?admin_key=YOUR_SECRET_KEY
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from services import pinterest as pin  # noqa: E402


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


async def cmd_whoami(_: argparse.Namespace) -> None:
    _print(
        {
            "configured": pin.is_configured(),
            "redirect_uri": pin.redirect_uri(),
            "token_file": str(pin.token_path()),
            "account": await pin.get_user_account(),
        }
    )


async def cmd_boards(_: argparse.Namespace) -> None:
    data = await pin.list_boards()
    items = data.get("items") or data.get("boards") or data
    _print(items)


async def cmd_create_board(args: argparse.Namespace) -> None:
    created = await pin.create_board(
        name=args.name,
        description=args.description or "",
        privacy=args.privacy,
    )
    _print(created)


async def cmd_pin_product(args: argparse.Namespace) -> None:
    # Local DB if available, else live API
    detail = None
    try:
        from database import SessionLocal, init_db
        from models import Product

        init_db()
        db = SessionLocal()
        try:
            p = (
                db.query(Product)
                .filter(Product.slug == args.slug.strip(), Product.active.is_(True))
                .first()
            )
            if p:
                detail = p.to_detail()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        print(f"# local DB skipped: {exc}", file=sys.stderr)

    if detail is None:
        import httpx

        base = pin.public_base()
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{base}/api/products/by-slug/{args.slug.strip()}")
            r.raise_for_status()
            detail = r.json()

    payload = pin.product_pin_payload(detail)
    if args.dry_run:
        _print({"dry_run": True, "board_id": args.board_id, **payload})
        return
    if not payload.get("image_url"):
        raise SystemExit("Product has no image_url")
    created = await pin.create_pin(
        board_id=args.board_id,
        title=payload["title"],
        description=payload["description"],
        link=payload["link"],
        image_url=payload["image_url"],
        alt_text=payload["alt_text"],
    )
    _print({"ok": True, "pin": created, "product": payload})


def cmd_oauth_url(_: argparse.Namespace) -> None:
    if not pin.is_configured():
        raise SystemExit("Set PINTEREST_CLIENT_ID and PINTEREST_CLIENT_SECRET in .env")
    # State-bound URL still requires going through the server start endpoint
    # for signature; print the start path instead of a fake state.
    secret = __import__("os").getenv("SECRET_KEY", "")
    if not secret:
        print("Set SECRET_KEY then open:", file=sys.stderr)
        print(f"{pin.public_base()}/api/pinterest/oauth/start?admin_key=YOUR_SECRET_KEY")
        return
    print(f"{pin.public_base()}/api/pinterest/oauth/start?admin_key={secret}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pinterest CLI for The Books Wanderer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="Show connected Pinterest account")
    sub.add_parser("boards", help="List boards")
    sub.add_parser("oauth-url", help="Print OAuth start URL (uses SECRET_KEY)")

    p_board = sub.add_parser("create-board", help="Create a board")
    p_board.add_argument("name")
    p_board.add_argument("--description", default="")
    p_board.add_argument("--privacy", default="PUBLIC", choices=["PUBLIC", "PROTECTED", "SECRET"])

    p_pin = sub.add_parser("pin-product", help="Pin a catalog product to a board")
    p_pin.add_argument("slug")
    p_pin.add_argument("--board-id", required=True)
    p_pin.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.cmd == "oauth-url":
        cmd_oauth_url(args)
        return
    handlers = {
        "whoami": cmd_whoami,
        "boards": cmd_boards,
        "create-board": cmd_create_board,
        "pin-product": cmd_pin_product,
    }
    asyncio.run(handlers[args.cmd](args))


if __name__ == "__main__":
    main()
