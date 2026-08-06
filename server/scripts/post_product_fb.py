#!/usr/bin/env python3
"""
Promote a live catalog product on the Facebook Page.

Usage (from server/, with .env + venv):

  python scripts/post_product_fb.py hollow-kitten-bookmark --dry-run
  python scripts/post_product_fb.py wooden-reading-tracker
  python scripts/post_product_fb.py kindle-magnetic-sleeve --campaign fb_organic_kindle
  python scripts/post_product_fb.py butterfly-metal-bookmark --video path/to/promo.mp4

Requires: FB_PAGE_ID, FB_PAGE_TOKEN (see docs/FACEBOOK.md)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB_POST = Path(__file__).resolve().parent / "fb_post.py"
DEFAULT_BASE = "https://thebookswanderer.com"


def _fetch_product(base: str, slug: str) -> dict:
    url = f"{base.rstrip('/')}/api/products/by-slug/{slug}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _abs_image(base: str, image_url: str) -> str:
    if not image_url:
        return ""
    if image_url.startswith("http://") or image_url.startswith("https://"):
        return image_url
    return f"{base.rstrip('/')}/{image_url.lstrip('/')}"


def _money(n: float) -> str:
    return f"${n:.2f}"


def build_message(p: dict, *, base: str, campaign: str) -> str:
    title = (p.get("title") or "Product").strip()
    desc = (p.get("description") or "").strip()
    # First sentence only for caption length
    blurb = desc.split(". ")[0].strip()
    if blurb and not blurb.endswith("."):
        blurb += "."
    price = float(p.get("price_usd") or 0)
    price_max = float(p.get("price_max_usd") or price)
    if price_max > price:
        price_line = f"From {_money(price)} · {p.get('category') or 'Collection'}"
    else:
        price_line = f"{_money(price)} · {p.get('category') or 'Collection'}"

    slug = p.get("slug") or ""
    link = (
        f"{base.rstrip('/')}/product.html?slug={slug}"
        f"&utm_source=facebook&utm_medium=organic&utm_campaign={campaign}"
    )

    parts = [
        blurb or f"Meet {title} — a small piece for the reading corner.",
        "",
        title,
        price_line,
        "",
        f"Shop: {link}",
        "",
        "For those who wander between pages.",
        "— The Books Wanderer",
    ]
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="Post a catalog product to Facebook.")
    ap.add_argument("slug", help="Product slug, e.g. hollow-kitten-bookmark")
    ap.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Store base URL (default {DEFAULT_BASE})",
    )
    ap.add_argument(
        "--campaign",
        default="",
        help="utm_campaign (default: fb_organic_<slug>)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass through to fb_post.py (no publish)",
    )
    ap.add_argument(
        "--text-only",
        action="store_true",
        help="Text + link only (no photo)",
    )
    ap.add_argument(
        "--video",
        type=Path,
        default=None,
        help="Local MP4 path — posts as Page video with product caption",
    )
    ap.add_argument(
        "--title",
        default="",
        help="Optional Facebook video title (defaults to product title)",
    )
    args = ap.parse_args()

    campaign = args.campaign.strip() or f"fb_organic_{args.slug.replace('-', '_')}"

    print(f"Fetching {args.slug} from {args.base} …")
    try:
        p = _fetch_product(args.base, args.slug)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Could not load product: {exc}")

    msg = build_message(p, base=args.base, campaign=campaign)
    img = _abs_image(args.base, p.get("image_url") or "")
    video_path = args.video.resolve() if args.video else None

    print("--- caption ---")
    print(msg)
    print("---")
    if video_path:
        if not video_path.is_file():
            sys.exit(f"Video not found: {video_path}")
        print("video:", video_path)
    elif img and not args.text_only:
        print("image:", img)
    else:
        print("image: (text-only)")

    if args.dry_run:
        cmd = [sys.executable, str(FB_POST), "--dry-run"]
    else:
        cmd = [sys.executable, str(FB_POST)]

    if video_path:
        title = (args.title or p.get("title") or "").strip()
        cmd += ["video", str(video_path), "--message", msg]
        if title:
            cmd += ["--title", title]
    elif args.text_only or not img:
        cmd += [
            "text",
            msg,
            "--link",
            f"{args.base.rstrip('/')}/product.html?slug={args.slug}",
        ]
    else:
        cmd += ["photo", img, "--message", msg]

    raise SystemExit(subprocess.call(cmd, cwd=str(ROOT)))


if __name__ == "__main__":
    main()
