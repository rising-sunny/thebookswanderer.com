"""One-piece hardcover (case wrap) for the Illustrated Quotes book: 1368 x 738 pt, from Lulu /cover-dimensions/ for
0850X0850FCSTDCW080CW444MXX at 44 pages (wrap 63 pt, spine 18 pt, too thin for text).

  python build_cover.py RACKHAM.pdf LEECH.pdf OUT.pdf [WORKDIR]
"""
import io
import subprocess
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageChops
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as RLFont
from reportlab.pdfgen import canvas

W, H, WRAP, TRIM, SPINE = 1368, 738, 63, 612, 18
GREEN, CREAM, RED, GOLD = (0.11, 0.23, 0.16), (0.97, 0.94, 0.88), (0.76, 0.3, 0.27), (0.85, 0.73, 0.45)
FONTS = Path(__file__).parent / "fonts"


def font(work, name):
    ttf = work / f"{name}.ttf"
    f = TTFont(FONTS / f"{name}.woff")
    f.flavor = None
    f.save(ttf)
    pdfmetrics.registerFont(RLFont(name, str(ttf)))


def leech(work, pdf, page):
    stem = work / f"cov{page}"
    subprocess.run(["pdftoppm", "-r", "400", "-f", str(page), "-l", str(page), "-jpeg", "-jpegopt", "quality=95", "-singlefile", pdf, str(stem)], check=True)
    im = Image.open(stem.with_suffix(".jpg")).convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((8, 8)))
    b = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 38 else 0).getbbox()
    return im.crop((b[0] + 6, b[1] + 6, b[2] - 6, b[1] + int((b[3] - b[1]) * 0.93)))


def draw_plate(c, im, cx, cy, maxw, maxh):
    s = min(maxw / im.width, maxh / im.height)
    w, h = im.width * s, im.height * s
    buf = io.BytesIO()
    im.resize((round(w / 72 * 300), round(h / 72 * 300)), Image.LANCZOS).save(buf, "JPEG", quality=90)
    buf.seek(0)
    c.setFillColorRGB(*CREAM)
    c.rect(cx - w / 2 - 6, cy - h / 2 - 6, w + 12, h + 12, fill=1, stroke=0)
    c.drawImage(ImageReader(buf), cx - w / 2, cy - h / 2, w, h)


def centred(c, x, y, text, f, size, color):
    c.setFillColorRGB(*color)
    c.setFont(f, size)
    c.drawCentredString(x, y, text)


def main():
    pdf_l, out = sys.argv[2], sys.argv[3]
    work = Path(sys.argv[4] if len(sys.argv) > 4 else "work")
    work.mkdir(parents=True, exist_ok=True)
    for n in ("eb-400-normal", "eb-400-italic", "eb-500-normal"):
        font(work, n)
    c = canvas.Canvas(out, pagesize=(W, H))
    c.setFillColorRGB(*GREEN)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    fx = WRAP + TRIM + SPINE            # front panel starts here
    fc, bc = fx + TRIM / 2, WRAP + TRIM / 2
    # front
    centred(c, fc, 600, "A CHRISTMAS CAROL", "eb-500-normal", 34, CREAM)
    centred(c, fc, 572, "The Illustrated Quotes", "eb-400-italic", 19, GOLD)
    draw_plate(c, leech(work, sys.argv[2], 93), fc, 340, 300, 330)
    centred(c, fc, 130, "CHARLES DICKENS", "eb-400-normal", 15, CREAM)
    centred(c, fc, 108, "Illustrations by John Leech and Arthur Rackham", "eb-400-italic", 11, GOLD)
    # back
    draw_plate(c, leech(work, sys.argv[2], 169), bc, 440, 200, 250)
    centred(c, bc, 270, "God bless Us, Every One!", "eb-400-italic", 24, GOLD)
    for i, ln in enumerate(["Twenty-one plates from the first edition (1843) and the Rackham",
                            "edition (1915) of Dickens's ghost story, each set beside the line",
                            "it illustrates. A square hardcover for the Christmas shelf."]):
        centred(c, bc, 225 - i * 17, ln, "eb-400-normal", 12, CREAM)
    centred(c, bc, 120, "Text and illustrations in the public domain", "eb-400-normal", 9, GOLD)
    c.showPage()
    c.save()


if __name__ == "__main__":
    main()
