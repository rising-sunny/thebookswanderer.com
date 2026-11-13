"""One-piece paperback cover for the 2027 Reading Challenge Journal (build_journal.py), A5, 56 pages.

Lulu /cover-dimensions/ for 0583X0827FCSTDPB080CW444GXX at 56 pages: 871 x 613 pt, so
bleed = (613 - 595.44) / 2 = 8.78 pt, spine = 871 - 2 x 419.76 - 2 x 8.78 = 13.92 pt (too thin for text).
Layout, left to right: bleed, back, spine, front, bleed. Green, gold and cream like the kit and its pins.

  python build_journal_cover.py FONTS_DIR OUT.pdf     # FONTS_DIR needs EBGaramond.ttf and EBGaramond-Italic.ttf
"""
import random
import sys
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

import build_kit as bk
from build_kit import SHELF, YEAR

GOLD = bk.HexColor("#c9a449")      # the brighter gold of the pins, so it reads on the green

W_PT, H_PT = 871.0, 613.0
TRIM_W, TRIM_H = 5.83 * 72, 8.27 * 72
BLEED = (H_PT - TRIM_H) / 2
SPINE = W_PT - 2 * TRIM_W - 2 * BLEED
GREEN, CREAM = bk.HexColor("#1c3326"), bk.HexColor("#faf5e9")
BACK_X, FRONT_X = BLEED, BLEED + TRIM_W + SPINE


def smallcaps(c, text, cx, y, size, color):
    parts, w = [], 0
    for ch in text:
        big = ch.isupper() or not ch.isalpha()
        f = size if big else size * 0.78
        parts.append((ch.upper(), f)); w += pdfmetrics.stringWidth(ch.upper(), "Garamond", f)
    x = cx - w / 2
    c.setFillColor(color)
    for ch, f in parts:
        c.setFont("Garamond", f); c.drawString(x, y, ch); x += pdfmetrics.stringWidth(ch, "Garamond", f)


def frame(c, x0, inset=34):
    c.setStrokeColor(GOLD); c.setLineWidth(1.4)
    c.rect(x0 + inset, BLEED + inset, TRIM_W - 2 * inset, TRIM_H - 2 * inset)
    c.setLineWidth(0.5)
    c.rect(x0 + inset + 5, BLEED + inset + 5, TRIM_W - 2 * inset - 10, TRIM_H - 2 * inset - 10)


def main(out):
    c = canvas.Canvas(str(out), pagesize=(W_PT, H_PT), initialFontName="Garamond", initialFontSize=10)
    c.setTitle(f"The {YEAR} Reading Challenge Journal: cover"); c.setAuthor("The Books Wanderer")
    c.setFillColor(GREEN); c.rect(0, 0, W_PT, H_PT, stroke=0, fill=1)
    # ---- front
    cx = FRONT_X + TRIM_W / 2
    frame(c, FRONT_X)
    smallcaps(c, "The", cx, BLEED + TRIM_H * 0.70, 20, GOLD)
    smallcaps(c, f"{YEAR} Reading", cx, BLEED + TRIM_H * 0.63, 36, CREAM)
    smallcaps(c, "Challenge Journal", cx, BLEED + TRIM_H * 0.565, 27, CREAM)
    c.setFont("GaramondIt", 13.5); c.setFillColor(GOLD)
    c.drawCentredString(cx, BLEED + TRIM_H * 0.51, "Fifty-two books, one a week, none of them assigned.")
    n, sw = 26, 8.2
    x, y = cx - n * sw / 2, BLEED + TRIM_H * 0.33
    rnd = random.Random(7)
    for i in range(n):
        h = rnd.randint(46, 78)
        c.setFillColor(SHELF[i % len(SHELF)]); c.setStrokeColor(GOLD); c.setLineWidth(0.5)
        c.rect(x + i * sw, y, sw - 1, h, stroke=1, fill=1)
    c.setStrokeColor(GOLD); c.setLineWidth(1.2); c.line(x - 8, y, x + n * sw + 6, y)
    c.setFont("Garamond", 12); c.setFillColor(CREAM)
    c.drawCentredString(cx, BLEED + TRIM_H * 0.17, "The Books Wanderer")
    # ---- spine: plain, with a thin gold rule (too thin for text)
    c.setStrokeColor(GOLD); c.setLineWidth(0.5)
    c.line(BLEED + TRIM_W + SPINE / 2, BLEED + 40, BLEED + TRIM_W + SPINE / 2, BLEED + TRIM_H - 40)
    # ---- back
    bx = BACK_X + TRIM_W / 2
    frame(c, BACK_X)
    smallcaps(c, "A year of reading", bx, BLEED + TRIM_H * 0.66, 19, CREAM)
    c.setFont("Garamond", 11.5); c.setFillColor(CREAM)
    lines = ["A checklist of 52 prompts, a bookshelf to colour,",
             "four bingo cards, a page for every month",
             "and room to review each book you finish.",
             "",
             "No deadlines. Just a place to keep count."]
    ty = BLEED + TRIM_H * 0.59
    for ln in lines:
        c.drawCentredString(bx, ty, ln); ty -= 17
    c.setFont("GaramondIt", 10.5); c.setFillColor(GOLD)
    c.drawCentredString(bx, BLEED + TRIM_H * 0.20, "A5 · 56 pages · paperback")
    c.setFont("Garamond", 11); c.setFillColor(CREAM)
    c.drawCentredString(bx, BLEED + TRIM_H * 0.155, "thebookswanderer.com")
    c.save()
    print(out, f"{W_PT} x {H_PT} pt; bleed {BLEED:.2f}, spine {SPINE:.2f}")


if __name__ == "__main__":
    main(Path(sys.argv[2]))
