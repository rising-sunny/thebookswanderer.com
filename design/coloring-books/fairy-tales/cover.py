"""Cover / title page in the manner of a Victorian title page: cream paper, ruled
border with Crane-style corner squares, one framed plate, quiet type."""
import io
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import build_pdf  # registers the fonts

GREEN = (0.13, 0.25, 0.19)
INK = (0.18, 0.16, 0.13)
RED = (0.62, 0.22, 0.15)
PAPER = (0.965, 0.94, 0.88)
LOGO = "/home/user/thebookswanderer.com/assets/logo-hero.webp"
PLATE = ("final/sleepingbeauty00cran-n9-color.jpg", 0.0, 0.855)  # crop off the verse box


def spaced(c, text, font, size, y, W, space, color):
    c.saveState(); c.setFillColorRGB(*color)
    t = c.beginText(); t.setFont(font, size); t.setCharSpace(space)
    width = c.stringWidth(text, font, size) + space * (len(text) - 1)
    t.setTextOrigin((W - width) / 2, y); t.textLine(text); c.drawText(t); c.restoreState()


def corner(c, x, y, s):
    """Square with an inset circle and dot, as on Crane's frames."""
    c.setStrokeColorRGB(*GREEN); c.setFillColorRGB(*PAPER); c.setLineWidth(0.9)
    c.rect(x - s / 2, y - s / 2, s, s, stroke=1, fill=1)
    c.circle(x, y, s * 0.3, stroke=1, fill=0)
    c.setFillColorRGB(*RED); c.circle(x, y, s * 0.09, stroke=0, fill=1)


def rule(c, cx, y, half):
    c.setStrokeColorRGB(*GREEN); c.setLineWidth(0.6)
    c.line(cx - half, y, cx - 7, y); c.line(cx + 7, y, cx + half, y)
    p = c.beginPath(); p.moveTo(cx, y + 4); p.lineTo(cx + 4, y); p.lineTo(cx, y - 4); p.lineTo(cx - 4, y); p.close()
    c.setFillColorRGB(*RED); c.drawPath(p, stroke=0, fill=1)


def draw_cover(c, W, H, paper=True, inset=24):
    if paper:
        c.setFillColorRGB(*PAPER); c.rect(0, 0, W, H, stroke=0, fill=1)
    o, i = inset, inset + 7
    c.setStrokeColorRGB(*GREEN)
    c.setLineWidth(1.4); c.rect(o, o, W - 2 * o, H - 2 * o)
    c.setLineWidth(0.5); c.rect(i, i, W - 2 * i, H - 2 * i)
    for x in (o + 3.5, W - o - 3.5):
        for y in (o + 3.5, H - o - 3.5):
            corner(c, x, y, 17)

    spaced(c, "COLOR THE", "SansB", 11, H - 86, W, 4.5, GREEN)
    c.setFillColorRGB(*INK); c.setFont("SerifI", 56)
    c.drawCentredString(W / 2, H - 142, "Fairy Tales")
    rule(c, W / 2, H - 163, 70)

    path, top, bottom = PLATE
    im = Image.open(path).convert("RGB")
    im = im.crop((0, int(im.height * top), im.width, int(im.height * bottom)))
    pw = 4.75 * 72; ph = pw * im.height / im.width
    px, py = (W - pw) / 2, H - 186 - ph
    buf = io.BytesIO(); im.resize((int(pw / 72 * 300), int(ph / 72 * 300)), Image.LANCZOS).save(buf, "JPEG", quality=88)
    buf.seek(0)
    c.setStrokeColorRGB(*GREEN); c.setLineWidth(0.5); c.rect(px - 7, py - 7, pw + 14, ph + 14)
    c.drawImage(ImageReader(buf), px, py, pw, ph)
    c.setLineWidth(1.1); c.rect(px, py, pw, ph)

    y = py - 38
    c.setFillColorRGB(*INK); c.setFont("Serif", 15)
    c.drawCentredString(W / 2, y, "Twenty-four plates by Walter Crane")
    c.setFillColorRGB(0.38, 0.35, 0.3); c.setFont("SerifI", 12)
    c.drawCentredString(W / 2, y - 20, "from the first editions of 1873–1876,")
    c.drawCentredString(W / 2, y - 36, "each with its line drawing to color")
    # the round logo, centred between the subtitle and the border
    top, bottom = y - 36 - 16, i + 14
    d = min(96, top - bottom)
    c.drawImage(ImageReader(round_logo(int(d / 72 * 300))), (W - d) / 2, bottom + (top - bottom - d) / 2, d, d, mask="auto")


def round_logo(px):
    """The shop logo cut to its circle, so the white square corners disappear."""
    from PIL import ImageDraw, ImageOps
    im = Image.open(LOGO).convert("RGB")
    box = ImageOps.invert(im.convert("L")).point(lambda v: 255 if v > 24 else 0).getbbox()
    im = im.crop(box).resize((px, px), Image.LANCZOS)
    alpha = Image.new("L", (px * 4, px * 4), 0)
    ImageDraw.Draw(alpha).ellipse((0, 0, px * 4 - 1, px * 4 - 1), fill=255)
    im.putalpha(alpha.resize((px, px), Image.LANCZOS))
    buf = io.BytesIO(); im.save(buf, "PNG"); buf.seek(0)
    return buf


if __name__ == "__main__":
    c = canvas.Canvas("cover.pdf", pagesize=letter); draw_cover(c, *letter); c.showPage(); c.save()
