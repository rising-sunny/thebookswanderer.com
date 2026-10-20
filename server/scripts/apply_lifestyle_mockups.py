#!/usr/bin/env python3
"""Add reviewed AI lifestyle images without replacing existing product photos.

Default is dry-run. Run --apply on the VPS after assets have been deployed.
Changes only gallery_json; never publishes to social networks or imports products.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from dotenv import load_dotenv

load_dotenv(ROOT / "server/.env")


def image_urls(spec, root):
    urls = []
    for image in spec["images"]:
        url = image["url"]
        if not url.startswith("/assets/products/") or not url.endswith(".jpg"):
            raise ValueError("Only local product JPEG paths are supported")
        path = (root / url.lstrip("/")).resolve()
        if not path.is_relative_to((root / "assets/products").resolve()):
            raise ValueError("Image escaped product assets directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != image["sha256"]:
            raise ValueError("Image checksum mismatch")
        urls.append(url)
    if not urls or len(urls) != len(set(urls)):
        raise ValueError("Empty or duplicate image list")
    return urls


def prepare(db, products, specs, root):
    changes = []
    seen = set()
    for spec in specs:
        slug = spec["slug"]
        if slug in seen:
            raise ValueError("Duplicate product slug")
        seen.add(slug)
        urls = image_urls(spec, root)
        product = db.query(products).filter(products.slug == slug).one_or_none()
        if product is None or not product.active:
            raise ValueError(f"Active product not found: {slug}")
        before = product.gallery_json
        existing = json.loads(before or "[]")
        if not isinstance(existing, list) or not all(isinstance(u, str) for u in existing):
            raise ValueError(f"Unexpected gallery shape: {slug}")
        # Match the model's fallback for an empty gallery_json value.
        if not before and product.image_url:
            existing = [product.image_url]
        if all(u in existing for u in urls):
            continue  # Idempotent, including preservation of original ordering.
        after = json.dumps(urls + [u for u in existing if u not in urls])
        changes.append({"slug": slug, "before": before, "after": after})
    return changes


def apply_changes(db, products, changes):
    try:
        for change in changes:
            count = db.query(products).filter(
                products.slug == change["slug"],
                products.gallery_json == change["before"],
            ).update({products.gallery_json: change["after"]}, synchronize_session=False)
            if count != 1:
                raise ValueError("Gallery changed since validation; refusing overwrite")
        db.commit()
    except Exception:
        db.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from database import SessionLocal
    from models import Product

    manifest = json.loads((Path(__file__).parent / "lifestyle_mockups_20261020.json").read_text())
    with SessionLocal() as db:
        try:
            changes = prepare(db, Product, manifest["products"], ROOT)
            print(json.dumps({"mode": "apply" if args.apply else "dry-run", "changed_products": len(changes), "slugs": [c["slug"] for c in changes]}))
            if args.apply and changes:
                backup_dir = ROOT / "server/data/lifestyle-gallery-backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup = backup_dir / f"{stamp}.json"
                fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as out:
                    json.dump({"changes": changes}, out, indent=2)
                apply_changes(db, Product, changes)
                print("Applied gallery changes; backup:", backup.name)
            elif args.apply:
                print("Already applied; no writes needed")
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
