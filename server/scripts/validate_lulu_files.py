#!/usr/bin/env python3
"""Ask Lulu to validate a printed product's interior and cover PDFs. Changes nothing.

  python scripts/validate_lulu_files.py color-the-fairy-tales-printed

Run it after uploading both files at /admin/digital/ and before activating the
product with scripts/digital_products.py. Lulu fetches the files through the
signed /api/print-files/ URLs; the URLs are never printed.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import Product  # noqa: E402
from services import digital, lulu  # noqa: E402


async def validate(kind: str, name: str, package: str, pages: int | None) -> dict:
    base = (os.getenv("PUBLIC_BASE_URL") or "https://thebookswanderer.com").rstrip("/")
    payload = {"source_url": lulu.file_url(base, name), "pod_package_id": package}
    if kind == "cover":
        payload["interior_page_count"] = pages
    record = await lulu.request("POST", f"/validate-{kind}/", payload)
    for _ in range(90):
        result = await lulu.request("GET", f"/validate-{kind}/{record['id']}/")
        if result.get("status") == "ERROR":
            raise ValueError(re.sub(r"https?://\S+", "[url]", str(result.get("errors", []))))
        if result.get("status") == "NORMALIZED":
            return result
        await asyncio.sleep(10)
    raise TimeoutError(f"{kind} validation still pending; run again later")


async def main(slug: str) -> int:
    with SessionLocal() as db:
        p = db.query(Product).filter(Product.slug == slug, Product.supplier == lulu.SUPPLIER).first()
        if not p or not p.lulu_package:
            print(f"{slug}: no printed product with a Lulu package")
            return 1
        for v in p.active_variants():
            if not (digital.file_path(v.digital_file) and digital.file_path(v.print_cover)):
                print(f"{v.name}: upload the interior and cover at /admin/digital/ first")
                return 1
            interior = await validate("interior", v.digital_file, p.lulu_package, None)
            pages = int(interior.get("page_count") or 0)
            print(f"{v.name}: interior NORMALIZED, {pages} pages")
            await validate("cover", v.print_cover, p.lulu_package, pages)
            print(f"{v.name}: cover NORMALIZED")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    try:
        raise SystemExit(asyncio.run(main(sys.argv[1])))
    except Exception as exc:  # provider messages can carry signed URLs
        print(re.sub(r"https?://\S+", "[url]", str(exc)), file=sys.stderr)
        raise SystemExit(1)
