"""Copy the Printify mockups used by active products to /assets/products/printify-mirror/.

Run on every deploy (deploy/remote-setup.sh); files already present are skipped. Only JPEG/PNG
responses under 15 MB from images-api.printify.com are saved. See services/image_mirror.py.

  python scripts/mirror_printify_images.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import SessionLocal  # noqa: E402
from models import Product  # noqa: E402
from services import image_mirror as mirror  # noqa: E402

MAX = 15 * 1024 * 1024


def urls() -> set[str]:
    db = SessionLocal()
    try:
        found = set()
        for p in db.query(Product).filter(Product.active.is_(True)).all():
            for u in [p.image_url, *p.gallery(), *[v.image_url for v in p.active_variants()]]:
                if mirror.needs_mirror(u or ""):
                    found.add(u)
        return found
    finally:
        db.close()


def fetch(url: str, dest: Path) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "TheBooksWanderer-image-mirror/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        kind = r.headers.get("Content-Type", "")
        data = r.read(MAX + 1)
    if r.status != 200 or not kind.startswith(("image/jpeg", "image/png")) or len(data) > MAX or len(data) < 1000:
        return False
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".mirror-")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, dest)
    return True


def main() -> None:
    mirror.DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(mirror.DIR, 0o755)
    wanted = urls()
    new = failed = 0
    for url in sorted(wanted):
        dest = mirror.DIR / mirror.filename(url)
        if dest.is_file():
            continue
        try:
            if fetch(url, dest):
                new += 1
            else:
                failed += 1
        except Exception:  # noqa: BLE001
            failed += 1
    print(f"printify mirror: {len(wanted)} images in use, {new} new, {failed} failed")


if __name__ == "__main__":
    main()
