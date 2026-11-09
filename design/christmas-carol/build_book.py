"""Interior of "A Christmas Carol: The Illustrated Quotes", 8.5 x 8.5 in hardcover (44 pages, no bleed).

  python build_book.py RACKHAM.pdf LEECH.pdf OUT.pdf [WORKDIR]

RACKHAM.pdf / LEECH.pdf are the Internet Archive scans (christmascar00dick, 1843christmascar00dickuoft). Needs poppler's
pdftoppm, Pillow, reportlab and fontTools. Plates and Dickens's text are public domain; quotes are verbatim (Gutenberg #46).
Layout: p1 title; then 21 spreads, plate on the left page and its line on the right; p44 closing page.
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

S = 612  # 8.5 in in points
INK, RED, GREEN, MUTE = (0.2, 0.16, 0.13), (0.59, 0.15, 0.15), (0.18, 0.32, 0.23), (0.55, 0.47, 0.39)
FONTS = Path(__file__).parent / "fonts"

# (source, page, crop box as fractions of the page or None, stave, quote)
PLATES = [
    ("r", 35, None, "Stave I", "…the clerk… went down a slide on Cornhill, at the end of a lane of boys, twenty times, in honour of its being Christmas Eve."),
    ("r", 41, None, "Stave I", "Nobody under the bed; nobody in the closet; nobody in his dressing-gown, which was hanging up in a suspicious attitude against the wall."),
    ("r", 8, None, "Stave I", "“How now!” said Scrooge, caustic and cold as ever. “What do you want with me?”"),
    ("l", 40, None, "Stave I", "“I wear the chain I forged in life,” replied the Ghost. “I made it link by link, and yard by yard; I girded it on of my own free will, and of my own free will I wore it.”"),
    ("r", 50, None, "Stave I", "“You travel fast?” said Scrooge. “On the wings of the wind,” replied the Ghost."),
    ("l", 53, (0.05, 0.31, 0.95, 0.96), "Stave I", "Every one of them wore chains like Marley’s Ghost; some few (they might be guilty governments) were linked together; none were free."),
    ("r", 55, None, "Stave I", "The air was filled with phantoms, wandering hither and thither in restless haste, and moaning as they went."),
    ("l", 89, (0.05, 0.45, 0.95, 0.96), "Stave II", "…a great extinguisher for a cap, which it now held under its arm."),
    ("l", 8, None, "Stave II", "“Why, it’s old Fezziwig! Bless his heart; it’s Fezziwig alive again!”"),
    ("r", 79, None, "Stave II", "Then old Fezziwig stood out to dance with Mrs. Fezziwig."),
    ("l", 93, None, "Stave III", "“I am the Ghost of Christmas Present,” said the Spirit. “Look upon me!”"),
    ("r", 105, None, "Stave III", "There was nothing very cheerful in the climate or the town, and yet was there an air of cheerfulness abroad."),
    ("r", 89, None, "Stave III", "…the centre of a flushed and boisterous group, just in time to greet the father, who came home attended by a man laden with Christmas toys and presents."),
    ("r", 93, None, "Stave III", "Then the shouting and the struggling, and the onslaught that was made on the defenceless porter!"),
    ("r", 131, None, "Stave III", "The way he went after that plump sister in the lace tucker, was an outrage on the credulity of human nature."),
    ("r", 118, None, "Stave III", "Oh, a wonderful pudding!"),
    ("l", 137, (0.05, 0.40, 0.95, 0.96), "Stave III", "“This boy is Ignorance. This girl is Want. Beware them both, and all of their degree.”"),
    ("r", 147, None, "Stave IV", "“Well!” said the first. “Old Scratch has got his own at last, hey?”"),
    ("r", 155, None, "Stave IV", "“What do you call this?” said Joe. “Bed-curtains!”"),
    ("l", 169, None, "Stave IV", "“Spirit!” he cried, tight clutching at its robe, “hear me! I am not the man I was.”"),
    ("r", 173, (0.02, 0.02, 0.98, 0.47), "Stave V", "Best and happiest of all, the Time before him was his own, to make amends in!"),
]


def register():
    for name in ("eb-400-normal", "eb-400-italic", "eb-500-normal"):
        ttf = Path(sys.argv[3]).parent / f"{name}.ttf"
        f = TTFont(FONTS / f"{name}.woff")
        f.flavor = None
        f.save(ttf)
        pdfmetrics.registerFont(RLFont(name, str(ttf)))


def plate(work, src, page, crop):
    pdf = sys.argv[1] if src == "r" else sys.argv[2]
    stem = work / f"{src}{page}"
    if not stem.with_suffix(".jpg").exists():
        subprocess.run(["pdftoppm", "-r", "400", "-f", str(page), "-l", str(page), "-jpeg", "-jpegopt", "quality=95", "-singlefile", pdf, str(stem)], check=True)
    im = Image.open(stem.with_suffix(".jpg")).convert("RGB")
    if crop:
        w, h = im.size
        im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    bg = Image.new("RGB", im.size, im.getpixel((8, 8)))
    box = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 38 else 0).getbbox()
    if src == "l" and not crop:  # Leech colour plates: drop the publisher's imprint line
        box = (box[0], box[1], box[2], box[1] + int((box[3] - box[1]) * 0.93))
    pad = 20
    return im.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad), min(im.height, box[3] + pad)))


def wrap(c, text, font, size, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if c.stringWidth(t, font, size) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


def centred(c, y, text, font, size, color):
    c.setFillColorRGB(*color)
    c.setFont(font, size)
    c.drawCentredString(S / 2, y, text)


def main():
    out, work = sys.argv[3], Path(sys.argv[4] if len(sys.argv) > 4 else "work")
    work.mkdir(parents=True, exist_ok=True)
    register()
    c = canvas.Canvas(out, pagesize=(S, S))
    # p1 title
    centred(c, 400, "A CHRISTMAS CAROL", "eb-500-normal", 40, GREEN)
    c.setStrokeColorRGB(*RED); c.setLineWidth(1.2); c.line(S / 2 - 50, 378, S / 2 + 50, 378)
    centred(c, 340, "The Illustrated Quotes", "eb-400-italic", 24, RED)
    centred(c, 270, "Charles Dickens", "eb-400-normal", 16, INK)
    centred(c, 232, "Illustrations by John Leech (1843) and Arthur Rackham (1915)", "eb-400-normal", 12, MUTE)
    c.showPage()
    for src, page, crop, stave, quote in PLATES:
        im = plate(work, src, page, crop)
        # left page: the plate, fitted into a 4.4 x 6.6 in area
        bw, bh = 504, 470
        s = min(bw / im.width, bh / im.height)
        w, h = im.width * s, im.height * s
        x, y = (S - w) / 2, (S - h) / 2 + 6
        px = (round(w / 72 * 300), round(h / 72 * 300))
        buf = io.BytesIO()
        im.resize(px, Image.LANCZOS).save(buf, "JPEG", quality=90)
        buf.seek(0)
        c.drawImage(ImageReader(buf), x, y, w, h)
        c.setStrokeColorRGB(*MUTE); c.setLineWidth(0.5); c.rect(x, y, w, h)
        c.showPage()
        # right page: stave and line
        centred(c, 470, stave.upper(), "eb-500-normal", 12, RED)
        c.setStrokeColorRGB(*RED); c.setLineWidth(0.8); c.line(S / 2 - 24, 455, S / 2 + 24, 455)
        size = 28 if len(quote) < 60 else 23 if len(quote) < 130 else 19
        lines = wrap(c, quote, "eb-400-italic", size, 420)
        y = 330 + (len(lines) * size * 1.4) / 2
        for ln in lines:
            centred(c, y, ln, "eb-400-italic", size, INK)
            y -= size * 1.4
        centred(c, 110, "A CHRISTMAS CAROL · CHARLES DICKENS", "eb-400-normal", 9, MUTE)
        c.showPage()
    # p44 closing
    centred(c, 330, "God bless Us, Every One!", "eb-400-italic", 28, RED)
    centred(c, 120, "Text by Charles Dickens, 1843. Illustrations by John Leech (1843) and Arthur Rackham (1915).", "eb-400-normal", 9, MUTE)
    centred(c, 106, "All in the public domain; reproduced from scans of the 1843 and 1915 editions.", "eb-400-normal", 9, MUTE)
    c.showPage()
    c.save()


if __name__ == "__main__":
    main()
