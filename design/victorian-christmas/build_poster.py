"""Poster files from the Met's public-domain lithograph "Christmas Eve (Kerstnacht)", Theodorus van Hoytema, 1894
(Met object 856909, Open Access). The printed image is cropped from the sheet and set on a paper-tone field
with a small museum-style caption, one file per Printify aspect ratio.

  python build_poster.py ORIGINAL.jpg OUT_DIR [fonts_dir]     # fonts_dir needs EBGaramond.ttf (variable)
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
FONTS = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).parent / "fonts"
BOX = (285, 255, 2345, 3605)           # the printed image with its thin frame, inside the sheet's own margin
PAPER = (236, 222, 200)
INK = (88, 76, 64)


def font(size, weight=450):
    f = ImageFont.truetype(str(FONTS / "EBGaramond.ttf"), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def poster(width, name, height=6000, margin=0.14):
    art = Image.open(SRC).convert("RGB").crop(BOX)
    scale = min((width * (1 - 2 * margin)) / art.width, (height * 0.80) / art.height)
    art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
    img = Image.new("RGB", (width, height), PAPER)
    top = int((height - art.height) * 0.40)
    img.paste(art, ((width - art.width) // 2, top))
    d = ImageDraw.Draw(img)
    cap = font(int(width * 0.022), 480)
    sub = font(int(width * 0.017), 400)
    y = top + art.height + int(height * 0.035)
    for text, f, dy in (("CHRISTMAS EVE  (KERSTNACHT)", cap, 0), ("Theodorus van Hoytema  ·  1894  ·  lithograph", sub, int(width * 0.04))):
        d.text(((width - d.textlength(text, font=f)) / 2, y + dy), text, font=f, fill=INK)
    img.save(OUT / f"{name}.png", optimize=True)
    img.resize((width // 8, height // 8), Image.LANCZOS).save(OUT / f"{name}-preview.jpg", quality=88)
    print(name, img.size, f"art upscaled x{scale:.2f}")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    poster(4000, "kerstnacht-poster-2x3")
    poster(4500, "kerstnacht-poster-3x4")
    poster(4800, "kerstnacht-poster-4x5")
