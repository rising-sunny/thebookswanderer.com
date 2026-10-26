"""One-piece Lulu cover for the Audubon mosaic books, A4 paperback, 32 pages:
1218 x 860 pt from Lulu /cover-dimensions/ (9 pt bleed, 9.4 pt spine, too thin for text)."""
import io
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import cover_mosaic as cm
from cover_mosaic import VOLUMES, INK, GREY, PAPER, rule, corner, draw_front
from cover import round_logo
import build_pdf
import books

COVER_W, COVER_H, BLEED = 1218, 860, 9
TRIM_W, TRIM_H = 595.28, 841.89
SPINE = COVER_W - 2 * BLEED - 2 * TRIM_W


def png(im):
    buf = io.BytesIO(); im.save(buf, "PNG"); buf.seek(0)
    return ImageReader(buf)


def back(c, W, H, name):
    v = VOLUMES[name]; acc = v["accent"]; plates = {"red": books.RED, "blue": books.BLUE}[name]
    o, i = 36, 43
    c.setStrokeColorRGB(*acc)
    c.setLineWidth(1.4); c.rect(o, o, W - 2 * o, H - 2 * o)
    c.setLineWidth(0.5); c.rect(i, i, W - 2 * i, H - 2 * i)
    for x in (o + 3.5, W - o - 3.5):
        for y in (o + 3.5, H - o - 3.5):
            corner(c, x, y, 15, acc)
    c.setFillColorRGB(*INK); c.setFont("SerifI", 30); c.drawCentredString(W / 2, H - 118, "Audubon's Birds")
    c.setFont("Serif", 14); c.drawCentredString(W / 2, H - 140, v["sub"])
    rule(c, W / 2, H - 156, 60, acc)
    text = (f"John James Audubon painted the birds of North America at life size, and his plates were printed "
            f"in London between 1827 and 1838. {v['count']} of them are here, each turned into a grid of small "
            "numbered squares. On the left of every spread is the finished picture with its colors. On the "
            "right is the grid you color, one square at a time, until the bird appears.")
    build_pdf.paragraph(c, text, 100, H - 196, W - 200, font="SerifI", size=12, leading=18.5)
    # a spread as it looks inside: the finished picture and part of its grid
    num = plates[1][0] if name == "red" else plates[9][0]
    art = Image.open(f"out/{name}-{num}-art.png").convert("RGB")
    grid = Image.open(f"out/{name}-{num}-color.png").convert("RGB")
    pw = 150; ph = pw * art.height / art.width; y0 = H - 510
    x1 = W / 2 - pw - 8; x2 = W / 2 + 8
    c.drawImage(png(art), x1, y0, pw, ph)
    # the same area of the grid page (right-hand page, so 2 mm right of centre)
    mm = 300 / 25.4
    gx0 = int(grid.width / 2 + 2 * mm - art.width / 2); gy0 = int(33 * mm + (219 * mm - art.height) / 2)
    c.drawImage(png(grid.crop((gx0, gy0, gx0 + art.width, gy0 + art.height))), x2, y0, pw, ph)
    c.setStrokeColorRGB(*acc); c.setLineWidth(0.5)
    c.rect(x1, y0, pw, ph); c.rect(x2, y0, pw, ph)
    names = [t for _, t, *_ in plates]
    c.setFillColorRGB(*GREY); c.setFont("Sans", 9.5)
    half = (len(names) + 1) // 2
    for k, line in enumerate((" · ".join(names[:half]), " · ".join(names[half:]))):
        c.drawCentredString(W / 2, y0 - 26 - 15 * k, line)
    d = 60
    c.drawImage(ImageReader(round_logo(int(d / 72 * 300))), i + 28, i + 26, d, d, mask="auto")
    c.setFillColorRGB(*acc); c.setFont("SansB", 9)
    c.drawString(i + 28 + d + 12, i + 26 + d / 2 - 3, "thebookswanderer.com")


def make(name):
    c = canvas.Canvas(f"{name}-cover-print.pdf", pagesize=(COVER_W, COVER_H), initialFontName="Sans")
    c.setFillColorRGB(*PAPER); c.rect(0, 0, COVER_W, COVER_H, stroke=0, fill=1)
    c.saveState(); c.translate(BLEED, BLEED); back(c, TRIM_W, TRIM_H, name); c.restoreState()
    c.saveState(); c.translate(BLEED + TRIM_W + SPINE, BLEED)
    draw_front(c, TRIM_W, TRIM_H, name, paper=False, inset=36); c.restoreState()
    c.showPage(); c.save()


if __name__ == "__main__":
    for name in VOLUMES:
        make(name)
