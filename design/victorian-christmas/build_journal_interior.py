"""Interior of the "Christmas Time" journal: A5 (5.83 x 8.27 in = 420 x 595 pt), no bleed, black and white,
a title page, a name page and ruled pages with a wider inside margin (mirrored for left/right pages).

  python build_journal_interior.py OUT.pdf [pages=120] [fonts_dir]   # fonts_dir needs EBGaramond.ttf
"""
import sys
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT = Path(sys.argv[1])
PAGES = int(sys.argv[2]) if len(sys.argv) > 2 else 120
FONTS = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Garamond", str(FONTS / "EBGaramond.ttf")))
W, H = 420, 595
INK, RULE = Color(0.15, 0.15, 0.15), Color(0.6, 0.6, 0.6)
INSIDE, OUTSIDE, TOP, BOTTOM, LEAD = 54, 40, 62, 62, 22


def centred(c, y, text, size, tracking=0):
    w = c.stringWidth(text, "Garamond", size) + tracking * (len(text) - 1)
    t = c.beginText((W - w) / 2, y)
    t.setFont("Garamond", size)
    t.setCharSpace(tracking)
    t.textOut(text)
    c.drawText(t)


c = canvas.Canvas(str(OUT), pagesize=(W, H), initialFontName="Garamond", initialFontSize=10)
c.setTitle("Christmas Time: A Journal")
for n in range(1, PAGES + 1):
    c.setFillColor(INK)
    if n == 1:
        centred(c, H * 0.56, "Christmas Time", 38)
        centred(c, H * 0.56 - 34, "A JOURNAL", 11, tracking=3)
    elif n == 2:
        pass
    elif n == 3:
        centred(c, H * 0.62, "This journal belongs to", 14)
        c.setStrokeColor(RULE); c.setLineWidth(0.6)
        c.line(90, H * 0.62 - 36, W - 90, H * 0.62 - 36)
    elif n > 3:
        left = INSIDE if n % 2 == 1 else OUTSIDE      # odd pages are on the right: the gutter is on their left
        right = OUTSIDE if n % 2 == 1 else INSIDE
        c.setStrokeColor(RULE); c.setLineWidth(0.5)
        y = H - TOP
        while y > BOTTOM:
            c.line(left, y, W - right, y)
            y -= LEAD
        c.setFont("Garamond", 8); c.setFillColor(Color(0.4, 0.4, 0.4))
        label = str(n)
        c.drawString((W - right - c.stringWidth(label, "Garamond", 8)) if n % 2 == 1 else left, 30, label)
    c.showPage()
c.save()
print(OUT, PAGES, "pages")
