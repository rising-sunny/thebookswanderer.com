"""Front cover for a hardcover journal from the Met's public-domain wood engraving "Christmas Time"
(Harvey Orrin Smith after W. Hemsley, Illustrated London News, 19 December 1857; Met object 700961, Open Access).
Front panel only, 5.83 x 8.27 in at 300 dpi (1749 x 2481 px, A5); the case-wrap layout waits for the printer's template.

  python build_journal_cover.py ORIGINAL.jpg OUT.png [fonts_dir]
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
FONTS = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).parent / "fonts"
BOX = (76, 76, 1911, 2498)                       # the engraved block, without the newspaper columns around it
W, H = 1749, 2481
GREEN, GOLD, CREAM = (28, 51, 38), (201, 164, 73), (250, 245, 233)


def font(name, size, weight=None):
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def centred(d, y, text, f, fill, spacing=0):
    w = d.textlength(text, font=f) + spacing * (len(text) - 1)
    x = (W - w) / 2
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + spacing


img = Image.new("RGB", (W, H), GREEN)
d = ImageDraw.Draw(img)
d.rectangle([60, 60, W - 60, H - 60], outline=GOLD, width=5)
d.rectangle([80, 80, W - 80, H - 80], outline=(110, 98, 60), width=2)
art = Image.open(SRC).convert("RGB").crop(BOX)
aw = 1170
art = art.resize((aw, round(art.height * aw / art.width)), Image.LANCZOS)
ax, ay = (W - aw) // 2, 205
d.rectangle([ax - 14, ay - 14, ax + aw + 14, ay + art.height + 14], fill=CREAM)
img.paste(art, (ax, ay))
y = ay + art.height + 80
centred(d, y, "Christmas Time", font("EBGaramond.ttf", 150, 450), CREAM)
centred(d, y + 200, "A  JOURNAL", font("EBGaramond.ttf", 44, 500), GOLD, spacing=14)
centred(d, H - 190, "thebookswanderer.com", font("EBGaramond-Italic.ttf", 44, 400), GOLD)
img.save(OUT, optimize=True)
img.resize((W // 3, H // 3), Image.LANCZOS).save(str(OUT).replace(".png", "-preview.jpg"), quality=88)
print(OUT, img.size, "art bottom at", ay + art.height)
