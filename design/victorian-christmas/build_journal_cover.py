"""Front cover for a hardcover journal from the Met's public-domain wood engraving "Christmas Time"
(Harvey Orrin Smith after W. Hemsley, Illustrated London News, 19 December 1857; Met object 700961, Open Access).
Front panel 5.83 x 8.27 in at 300 dpi (1749 x 2481 px, A5), plus the one-piece case-wrap PDF Lulu asks for:
1002 x 721 pt for 0583X0827FCSTDCW080CW444MXX / 0583X0827BWSTDCW060UW444MXX at 120 pages (/cover-dimensions/),
i.e. 63 pt wrap + 420 back + 36 spine + 420 front + 63 wrap.

  python build_journal_cover.py ORIGINAL.jpg OUT.png [fonts_dir]     # also writes OUT-wrap.pdf
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


# ---- one-piece case wrap (pt -> px at 300 dpi) -------------------------------------------------------------
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PT = 300 / 72
WRAP_W, WRAP_H, WRAP, TRIM_W, SPINE = 1002, 721, 63, 420, 36
wrap = Image.new("RGB", (round(WRAP_W * PT), round(WRAP_H * PT)), GREEN)
front_x = round((WRAP + TRIM_W + SPINE) * PT)
front_y = round(WRAP * PT)
wrap.paste(img, (front_x, front_y))
wd = ImageDraw.Draw(wrap)
# spine: the title reading top to bottom, as on US hardcovers
sp = Image.new("RGBA", (round(WRAP_H * PT), round(SPINE * PT)), (0, 0, 0, 0))
sd = ImageDraw.Draw(sp)
t1, t2 = "Christmas Time", "A  JOURNAL"
f1, f2 = font("EBGaramond.ttf", 64, 450), font("EBGaramond.ttf", 30, 500)
cy = sp.height // 2
x = (sp.width - sd.textlength(t1, font=f1) - 60 - sd.textlength(t2, font=f2)) / 2
sd.text((x, cy), t1, font=f1, fill=CREAM, anchor="lm")
sd.text((x + sd.textlength(t1, font=f1) + 60, cy), t2, font=f2, fill=GOLD, anchor="lm")
spine_x = round((WRAP + TRIM_W) * PT)
wrap.paste(sp.rotate(-90, expand=True), (spine_x, 0), sp.rotate(-90, expand=True))
# back cover
bx0, bx1 = round(WRAP * PT), round((WRAP + TRIM_W) * PT)
wd.rectangle([bx0 + 60, front_y + 60, bx1 - 60, front_y + round(595 * PT) - 60], outline=GOLD, width=5)
wd.rectangle([bx0 + 80, front_y + 80, bx1 - 80, front_y + round(595 * PT) - 80], outline=(110, 98, 60), width=2)
cx = (bx0 + bx1) // 2
fb, fi, fs = font("EBGaramond.ttf", 62, 450), font("EBGaramond-Italic.ttf", 50, 400), font("EBGaramond.ttf", 34, 400)
y = front_y + 700
for line in ("A place for the books,", "the notes and the quiet", "hours of the season."):
    wd.text((cx, y), line, font=fb, fill=CREAM, anchor="mm"); y += 95
wd.text((cx, y + 90), "120 ruled pages", font=fi, fill=GOLD, anchor="mm")
credit = ("Cover: \u201cChristmas Time,\u201d wood engraving by Harvey Orrin Smith after W. Hemsley,",
          "Illustrated London News, 19 December 1857.", "The Metropolitan Museum of Art, Open Access.")
yc = front_y + round(595 * PT) - 330
for line in credit:
    wd.text((cx, yc), line, font=fs, fill=(190, 178, 140), anchor="mm"); yc += 48
wd.text((cx, front_y + round(595 * PT) - 175), "thebookswanderer.com", font=fi, fill=GOLD, anchor="mm")
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as RLFont
pdfmetrics.registerFont(RLFont("Garamond", str(FONTS / "EBGaramond.ttf")))   # so no unembedded default font is listed
pdf = canvas.Canvas(str(OUT).replace(".png", "-wrap.pdf"), pagesize=(WRAP_W, WRAP_H), initialFontName="Garamond")
pdf.drawImage(ImageReader(wrap), 0, 0, WRAP_W, WRAP_H)
pdf.save()
wrap.resize((wrap.width // 4, wrap.height // 4), Image.LANCZOS).save(str(OUT).replace(".png", "-wrap-preview.jpg"), quality=88)
print("wrap", wrap.size, "px ->", WRAP_W, "x", WRAP_H, "pt")
