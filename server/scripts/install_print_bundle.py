#!/usr/bin/env python3
"""Install a printed book's PDFs from its encrypted bundle, validate them at Lulu, optionally activate.

  python scripts/install_print_bundle.py color-the-fairy-tales-printed
  python scripts/install_print_bundle.py color-the-fairy-tales-printed --activate

The bundle is assets/products/<slug>/print-bundle.enc: a zip with interior.pdf,
cover.pdf and manifest.json ({"pages": n, "sha256": {...}}), CMS-encrypted to the
server's release key (see print_release_cert.py). The product must exist first
(scripts/digital_products.py --apply <slug>). Creates no orders and no payments.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal  # noqa: E402
from models import Product  # noqa: E402
from services import digital, lulu  # noqa: E402
from validate_lulu_files import validate  # noqa: E402


def install(slug: str) -> tuple[dict, int]:
    private = digital.digital_dir() / ".release-private"
    key, bundle = private / "lost-manuscript.pem", ROOT.parent / "assets/products" / slug / "print-bundle.enc"
    if not key.is_file() or not bundle.is_file():
        raise ValueError("release key or encrypted bundle missing")
    files = {}
    with tempfile.TemporaryDirectory(prefix="bundle-", dir=private) as tmp:
        zipped = Path(tmp) / "bundle.zip"
        subprocess.run(["openssl", "cms", "-decrypt", "-binary", "-inform", "DER", "-inkey", str(key),
                        "-in", str(bundle), "-out", str(zipped)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with ZipFile(zipped) as z:
            if set(z.namelist()) != {"manifest.json", "interior.pdf", "cover.pdf"}:
                raise ValueError("unexpected bundle members")
            manifest = json.loads(z.read("manifest.json"))
            for kind in ("interior", "cover"):
                data = z.read(f"{kind}.pdf")
                digest = hashlib.sha256(data).hexdigest()
                if digest != manifest["sha256"][f"{kind}.pdf"] or not data.startswith(b"%PDF-"):
                    raise ValueError(f"{kind}: checksum mismatch or not a PDF")
                name = f"{slug}-{kind}-{digest[:12]}.pdf"
                target = digital.digital_dir() / name
                pending = target.with_suffix(".tmp")
                pending.write_bytes(data); os.chmod(pending, 0o640); pending.replace(target)
                files[kind] = name
    return files, int(manifest["pages"])


async def main(slug: str, activate: bool) -> int:
    with SessionLocal() as db:
        p = db.query(Product).filter(Product.slug == slug, Product.supplier == lulu.SUPPLIER).first()
        if not p or not p.lulu_package:
            print(f"{slug}: create it first with scripts/digital_products.py --apply {slug}")
            return 1
        files, pages = install(slug)
        for v in p.variants:
            v.digital_file, v.print_cover = files["interior"], files["cover"]
        db.commit()
        print(f"installed {files['interior']} and {files['cover']}")
        interior = await validate("interior", files["interior"], p.lulu_package, None)
        if int(interior.get("page_count") or 0) != pages:
            print(f"Lulu counted {interior.get('page_count')} pages, the manifest says {pages}")
            return 1
        print(f"interior NORMALIZED, {pages} pages")
        await validate("cover", files["cover"], p.lulu_package, pages)
        print("cover NORMALIZED")
        if activate:
            p.active = True
            db.commit()
            print(f"active: /products/{slug}")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    try:
        raise SystemExit(asyncio.run(main(args[0], "--activate" in sys.argv)))
    except Exception as exc:  # provider messages can carry signed URLs
        print(re.sub(r"https?://\S+", "[url]", str(exc)), file=sys.stderr)
        raise SystemExit(1)
