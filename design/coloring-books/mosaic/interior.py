"""Lulu interior for the Audubon mosaic books: A4, no bleed, 32 pages.
Title, how to color, a pencil test page, then every plate as a spread (finished
picture on the left, numbered grid on the right), the list of birds and blank grids."""
import sys, glob
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
sys.path.insert(0, "../pd")
import build_pdf  # registers the fonts
from cover import spaced, round_logo
from cover_mosaic import VOLUMES, INK, GREY, rule
import books

W, H = 595.28, 841.89
PAGES = 32
GUTTER = 2 * mm   # centre of every page moves this far away from the spine


def centre(page_no):
    """Odd pages are right-hand pages: their spine is on the left."""
    return W / 2 + (GUTTER if page_no % 2 else -GUTTER)


def title_page(c, n, v):
    cx = centre(n); acc = v["accent"]
    spaced(c, "A COLOR-BY-NUMBER BOOK", "SansB", 10, H - 230, W + 2 * (cx - W / 2), 4, acc)
    c.setFillColorRGB(*INK); c.setFont("SerifI", 46); c.drawCentredString(cx, H - 290, "Audubon's Birds")
    c.setFont("Serif", 17); c.drawCentredString(cx, H - 320, v["sub"])
    rule(c, cx, H - 342, 70, acc)
    c.setFillColorRGB(*GREY); c.setFont("SerifI", 12)
    c.drawCentredString(cx, H - 372, f"{v['count']} plates from The Birds of America")
    c.drawCentredString(cx, H - 388, "by John James Audubon, 1827–1838")
    spaced(c, v["volume"].upper(), "SansB", 8.5, H - 420, W + 2 * (cx - W / 2), 3, acc)
    d = 72
    c.drawImage(ImageReader(round_logo(int(d / 72 * 300))), cx - d / 2, 110, d, d, mask="auto")
    c.setFillColorRGB(*GREY); c.setFont("Sans", 9); c.drawCentredString(cx, 92, "thebookswanderer.com")


def heading(c, cx, y, text, acc):
    c.setFillColorRGB(*INK); c.setFont("SerifI", 24); c.drawCentredString(cx, y, text)
    rule(c, cx, y - 16, 50, acc)


def how_to(c, n, v):
    cx = centre(n); acc = v["accent"]
    heading(c, cx, H - 110, "How to color", acc)
    y = H - 160
    for p in ("Each picture comes as a pair. On the left is the finished picture with its colors. "
              "On the right is the grid you color.",
              "Every square has a number. Find that number in the key at the foot of the page and color "
              "the square to match. Squares with no number stay white.",
              "Colored pencils work best. Keep them sharp, as the squares are 3.5 mm wide. Markers can show "
              "through the paper, so slip a sheet of card behind the page if you use them.",
              "Your colors do not need to be exact. Get as close as your pencils allow, or choose your own."):
        y = build_pdf.paragraph(c, p, cx - 62 * mm, y, 124 * mm, font="Serif", size=11.5, leading=18) - 12
    heading(c, cx, y - 40, "About the plates", acc)
    y -= 90
    for p in ("John James Audubon set out to paint every bird of North America at life size. His pictures were "
              "engraved and colored by hand in London, most of them by Robert Havell, and published between "
              "1827 and 1838 as The Birds of America, in 435 plates.",
              "Each picture in this book starts from one of those plates. It was cut into a grid of 3,100 squares "
              "and its colors brought down to fourteen or fewer, so that it can be colored by number."):
        y = build_pdf.paragraph(c, p, cx - 62 * mm, y, 124 * mm, font="Serif", size=11.5, leading=18) - 12


def test_page(c, n, v):
    cx = centre(n); acc = v["accent"]
    heading(c, cx, H - 110, "Try your pencils", acc)
    c.setFillColorRGB(*GREY); c.setFont("SerifI", 11.5)
    c.drawCentredString(cx, H - 150, "Test each pencil here and write its name or number beside it.")
    s = 12 * mm; cols = 6; rows = 14; gapx = 26 * mm
    x0 = cx - (cols * gapx) / 2 + 2 * mm; y0 = H - 190
    c.setStrokeColorRGB(0.65, 0.65, 0.65); c.setLineWidth(0.6)
    for r in range(rows):
        for k in range(cols):
            x = x0 + k * gapx; y = y0 - r * (s + 4 * mm)
            c.rect(x, y - s, s, s)
            c.line(x + s + 2 * mm, y - s, x + gapx - 4 * mm, y - s)


def plate_page(c, path):
    c.drawImage(ImageReader(path), 0, 0, W, H)


def birds_page(c, n, v, plates, first):
    cx = centre(n); acc = v["accent"]
    heading(c, cx, H - 110, "The birds in this book", acc)
    y = H - 165
    for k, (num, title, *_) in enumerate(plates):
        page = first + 2 * k
        c.setFillColorRGB(*INK); c.setFont("Serif", 12.5); c.drawString(cx - 70 * mm, y, title)
        c.setFillColorRGB(*GREY); c.setFont("SerifI", 11)
        c.drawRightString(cx + 70 * mm, y, f"plate {num}, page {page}")
        c.setStrokeColorRGB(0.8, 0.78, 0.74); c.setLineWidth(0.4)
        c.line(cx - 70 * mm, y - 6, cx + 70 * mm, y - 6)
        y -= 30


def blank_grid(c, n, v):
    cx = centre(n); cell = 3.5 * mm; cols, rows = 50, 62
    c.setFillColorRGB(*INK); c.setFont("Serif", 17); c.drawCentredString(cx, H - 20 * mm - 6, "A grid of your own")
    c.setFillColorRGB(*GREY); c.setFont("SerifI", 10.5)
    c.drawCentredString(cx, H - 27 * mm - 4, "Draw a bird, or anything you like, one square at a time")
    x0 = cx - cols * cell / 2; top = H - 33 * mm - (219 * mm - rows * cell) / 2
    c.setStrokeColorRGB(0.72, 0.72, 0.72); c.setLineWidth(0.5)
    for k in range(cols + 1):
        c.line(x0 + k * cell, top, x0 + k * cell, top - rows * cell)
    for k in range(rows + 1):
        c.line(x0, top - k * cell, x0 + cols * cell, top - k * cell)


def build(name):
    v = VOLUMES[name]; plates = {"red": books.RED, "blue": books.BLUE}[name]
    c = canvas.Canvas(f"{name}-interior.pdf", pagesize=(W, H), initialFontName="Sans")
    n = 1
    def done():
        nonlocal n
        c.showPage(); n += 1
    title_page(c, n, v); done()
    how_to(c, n, v); done()
    test_page(c, n, v); done()
    first = n
    for num, *_ in plates:
        assert n % 2 == 0
        plate_page(c, f"out/{name}-{num}-solution.png"); done()
        plate_page(c, f"out/{name}-{num}-color.png"); done()
    if n % 2:                      # the list goes on a left-hand page
        done()
    birds_page(c, n, v, plates, first); done()
    while n <= PAGES:
        if n % 2:
            blank_grid(c, n, v)
        done()
    c.save()
    print(name, n - 1, "pages")


if __name__ == "__main__":
    for name in sys.argv[1:] or VOLUMES:
        build(name)
