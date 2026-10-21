"""Encode responsive homepage covers from the unchanged original PNG crops.

Run from any directory: python server/scripts/optimize_home_cover_images.py
Requires Pillow with WebP support. No supplier calls or storefront writes.
"""
from pathlib import Path
import hashlib
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
WIDTHS = (240, 400, 600, 800)

def main():
    report = []
    for name in ('notebook', 'commonplace'):
        source = ROOT / 'assets/products/home-atelier-preview' / f'{name}-front.png'
        with Image.open(source) as original:
            variants = []
            for width in WIDTHS:
                height = round(original.height * width / original.width)
                resized = original.resize((width, height), Image.Resampling.LANCZOS)
                target = ROOT / 'assets/products/home-atelier' / f'{name}-front-{width}.webp'
                resized.save(target, 'WEBP', quality=90, method=6)
                variants.append({'file':str(target.relative_to(ROOT)), 'width':width,
                                 'height':height, 'bytes':target.stat().st_size})
            report.append({'source':str(source.relative_to(ROOT)),
                           'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                           'source_bytes':source.stat().st_size, 'variants':variants})
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
