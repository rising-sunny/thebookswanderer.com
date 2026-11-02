#!/usr/bin/env python3
"""Install the three owner-requested, visibly labelled AI gallery illustrations."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install(db, *, apply=False, asset_dir=None):
    from models import Product
    from services import product_media as media

    product = db.get(Product, 73)
    if (not product or product.slug != "miniature-library"
            or product.cj_pid != "2501150522201605300"
            or not product.active or product.draft):
        raise SystemExit("Se detuvo: no se encontró la mini biblioteca publicada esperada.")
    folder = asset_dir or ROOT.parent / "assets/products/miniature-library-ai"
    manifest = json.loads((folder / "manifest.json").read_text())
    expected = {"reading-desk.webp", "reading-nook.webp", "detail.webp"}
    if len(manifest) != 3 or {item.get("file") for item in manifest} != expected:
        raise SystemExit("Se detuvo: el manifiesto no contiene las tres imágenes esperadas.")
    data = []
    for item in manifest:
        raw = (folder / item["file"]).read_bytes()
        if (not item.get("ai_generated") or not item.get("embedded_disclosure")
                or hashlib.sha256(raw).hexdigest() != item.get("sha256")):
            raise SystemExit("Se detuvo: una imagen no coincide con el archivo revisado.")
        media.validate_image(raw)
        data.append(raw)
    if apply:
        changed = media.append(db, product, media.revision(product), data, origin="ai", disclosed=True)
        print(json.dumps({"status": "updated" if changed else "already_installed", "product_id": product.id,
                          "gallery_images": len(media.gallery(product)), "hero_preserved": True}))
    else:
        print(json.dumps({"status": "preview", "product_id": product.id, "additional_images": 3,
                          "ai_disclosure_embedded": True, "hero_preserved": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from database import SessionLocal
    with SessionLocal() as db:
        install(db, apply=args.apply)


if __name__ == "__main__":
    main()
