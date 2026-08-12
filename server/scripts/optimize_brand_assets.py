#!/usr/bin/env python3
"""
Rebuild optimized brand assets from sources under assets/.

Inputs (expected):
  assets/brand/logo-master.png       full-resolution brand mark — NEVER written
  assets/social/facebook-cover.jpg   wide brand banner

Outputs:
  assets/logo.png              512² palette PNG (~150–200 KB)
  assets/logo.webp             512² WebP for CSS emblems (~30 KB)
  assets/logo-hero.webp        full-res WebP for the homepage medallion
  assets/favicon*.png / .ico
  assets/apple-touch-icon.png
  assets/og-default.jpg        1200×630 social share image

The master lives outside the output set on purpose: this script used to read
assets/logo.png and then overwrite it, so every run re-encoded its own 512px
output and the original resolution was lost for good.

Usage (from repo root):
  python server/scripts/optimize_brand_assets.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"


def main() -> None:
    src = ASSETS / "brand" / "logo-master.png"
    cover_path = ASSETS / "social" / "facebook-cover.jpg"
    if not src.is_file():
        raise SystemExit(
            f"Missing {src} — restore the full-resolution master before running. "
            "Do not point this at assets/logo.png; that is an output."
        )

    im = Image.open(src).convert("RGB")
    print(f"logo source: {im.size} {src.stat().st_size // 1024} KB")

    # Homepage medallion renders the mark at ~735 CSS px (and double that on
    # retina), so the 512px emblem asset was being upscaled and looked soft.
    im.save(ASSETS / "logo-hero.webp", format="WEBP", quality=88, method=6)
    print(f"  logo-hero.webp {(ASSETS / 'logo-hero.webp').stat().st_size // 1024} KB {im.size}")

    logo512 = im.resize((512, 512), Image.Resampling.LANCZOS)
    logo512.convert("P", palette=Image.Palette.ADAPTIVE, colors=192).save(
        ASSETS / "logo.png", format="PNG", optimize=True
    )
    logo512.save(ASSETS / "logo.webp", format="WEBP", quality=85, method=6)
    print(f"  logo.png  {(ASSETS / 'logo.png').stat().st_size // 1024} KB")
    print(f"  logo.webp {(ASSETS / 'logo.webp').stat().st_size // 1024} KB")

    for size, name in (
        (32, "favicon-32.png"),
        (48, "favicon-48.png"),
        (180, "apple-touch-icon.png"),
    ):
        t = logo512.resize((size, size), Image.Resampling.LANCZOS)
        t.save(ASSETS / name, format="PNG", optimize=True)

    rgba = logo512.convert("RGBA")
    sizes = [(16, 16), (32, 32), (48, 48)]
    icons = [rgba.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    icons[0].save(ASSETS / "favicon.ico", format="ICO", sizes=sizes)
    print(f"  favicons + apple-touch-icon")

    if cover_path.is_file():
        cover = Image.open(cover_path).convert("RGB")
        tw, th = 1200, 630
        cw, ch = cover.size
        scale = min(tw / cw, th / ch)
        nw, nh = int(cw * scale + 0.5), int(ch * scale + 0.5)
        scaled = cover.resize((nw, nh), Image.Resampling.LANCZOS)
        bg = Image.new("RGB", (tw, th), (248, 242, 229))
        bg.paste(scaled, ((tw - nw) // 2, (th - nh) // 2))
        ImageDraw.Draw(bg).rectangle([0, 0, tw, 4], fill=(193, 145, 47))
        bg = ImageEnhance.Contrast(bg).enhance(1.02)
        out = ASSETS / "og-default.jpg"
        bg.save(out, format="JPEG", quality=88, optimize=True, progressive=True)
        bg.save(
            ASSETS / "social" / "og-default.jpg",
            format="JPEG",
            quality=88,
            optimize=True,
            progressive=True,
        )
        print(f"  og-default.jpg {out.stat().st_size // 1024} KB {bg.size}")
    else:
        print(f"  skip OG (missing {cover_path})")

    print("OK")


if __name__ == "__main__":
    main()
