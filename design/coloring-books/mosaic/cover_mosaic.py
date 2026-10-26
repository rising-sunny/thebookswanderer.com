"""Front cover for the Audubon mosaic books: cream paper, a plain double rule with
small square corners, the finished grid of one plate, quiet type and the round logo."""
import sys, io
import numpy as np
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
sys.path.insert(0, "../pd")
import build_pdf  # registers the fonts
from cover import spaced, round_logo

A4 = (595.28, 841.89)
INK = (0.18, 0.16, 0.13)
GREY = (0.38, 0.35, 0.3)
PAPER = (0.965, 0.94, 0.88)
VOLUMES = {
    "red": dict(accent=(0.55, 0.13, 0.20), plate=431, volume="Volume I", sub="Red and rose birds",
                count="Eleven"),
    "blue": dict(accent=(0.13, 0.24, 0.40), plate=217, volume="Volume II", sub="Blue and water birds",
                 count="Ten"),
}


def corner(c, x, y, s, accent):
    """Two nested squares, a nod to the grid inside."""
    c.setStrokeColorRGB(*accent); c.setFillColorRGB(*PAPER); c.setLineWidth(0.9)
    c.rect(x - s / 2, y - s / 2, s, s, stroke=1, fill=1)
    c.setFillColorRGB(*accent); c.rect(x - s * 0.2, y - s * 0.2, s * 0.4, s * 0.4, stroke=0, fill=1)


def rule(c, cx, y, half, accent):
    c.setStrokeColorRGB(*accent); c.setLineWidth(0.6)
    c.line(cx - half, y, cx - 6, y); c.line(cx + 6, y, cx + half, y)
    c.setFillColorRGB(*accent); c.rect(cx - 2.5, y - 2.5, 5, 5, stroke=0, fill=1)


def grid_picture(name, plate):
    """The finished grid as saved by mosaic.build, with the blank background on cream."""
    a = np.array(Image.open(f"out/{name}-{plate}-art.png").convert("RGB"))
    a[(a == 255).all(-1)] = [int(v * 255) for v in PAPER]
    return Image.fromarray(a)


def draw_front(c, W, H, name, paper=True, inset=24):
    v = VOLUMES[name]; acc = v["accent"]
    if paper:
        c.setFillColorRGB(*PAPER); c.rect(0, 0, W, H, stroke=0, fill=1)
    o, i = inset, inset + 7
    c.setStrokeColorRGB(*acc)
    c.setLineWidth(1.4); c.rect(o, o, W - 2 * o, H - 2 * o)
    c.setLineWidth(0.5); c.rect(i, i, W - 2 * i, H - 2 * i)
    for x in (o + 3.5, W - o - 3.5):
        for y in (o + 3.5, H - o - 3.5):
            corner(c, x, y, 15, acc)

    spaced(c, "A COLOR-BY-NUMBER BOOK", "SansB", 10, H - 82, W, 4, acc)
    c.setFillColorRGB(*INK); c.setFont("SerifI", 50)
    c.drawCentredString(W / 2, H - 136, "Audubon's Birds")
    c.setFont("Serif", 17); c.setFillColorRGB(*INK)
    c.drawCentredString(W / 2, H - 164, v["sub"])
    rule(c, W / 2, H - 182, 70, acc)

    im = grid_picture(name, v["plate"])
    pw = 300; ph = pw * im.height / im.width
    px, py = (W - pw) / 2, H - 206 - ph
    buf = io.BytesIO(); im.save(buf, "PNG"); buf.seek(0)
    c.drawImage(ImageReader(buf), px, py, pw, ph)
    c.setStrokeColorRGB(*acc); c.setLineWidth(0.5); c.rect(px - 8, py - 8, pw + 16, ph + 16)

    y = py - 40
    c.setFillColorRGB(*INK); c.setFont("Serif", 14)
    c.drawCentredString(W / 2, y, f"{v['count']} plates after John James Audubon")
    c.setFillColorRGB(*GREY); c.setFont("SerifI", 11.5)
    c.drawCentredString(W / 2, y - 18, "from The Birds of America, 1827–1838,")
    c.drawCentredString(W / 2, y - 33, "each as a numbered grid to color")
    spaced(c, v["volume"].upper(), "SansB", 8.5, y - 56, W, 3, acc)
    top, bottom = y - 56 - 14, i + 14
    d = min(80, top - bottom)
    c.drawImage(ImageReader(round_logo(int(d / 72 * 300))), (W - d) / 2, bottom + (top - bottom - d) / 2, d, d, mask="auto")


if __name__ == "__main__":
    for name in VOLUMES:
        c = canvas.Canvas(f"cover-{name}.pdf", pagesize=A4); draw_front(c, *A4, name); c.showPage(); c.save()
