"""Lulu print files for 0850X1100FCSTDPB060UW444MXX, 52 pages:
interior (8.5 x 11, no bleed) and one-piece cover 1255 x 810 pt (Lulu /cover-dimensions/)."""
import io
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import build_pdf
import cover

COVER_W, COVER_H, BLEED = 1255, 810, 9
TRIM_W, TRIM_H = 612, 792
SPINE = COVER_W - 2 * BLEED - 2 * TRIM_W   # 13 pt: too thin for spine text


def jpeg(path, w_pt, h_pt, dpi=300, crop=None):
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop((0, int(im.height * crop[0]), im.width, int(im.height * crop[1])))
    buf = io.BytesIO()
    im.resize((int(w_pt / 72 * dpi), int(h_pt / 72 * dpi)), Image.LANCZOS).save(buf, "JPEG", quality=90)
    buf.seek(0)
    return ImageReader(buf)


def back(c, W, H):
    """Back panel, trim size, origin at its lower-left trim corner."""
    o, i = 36, 43
    c.setStrokeColorRGB(*cover.GREEN)
    c.setLineWidth(1.4); c.rect(o, o, W - 2 * o, H - 2 * o)
    c.setLineWidth(0.5); c.rect(i, i, W - 2 * i, H - 2 * i)
    for x in (o + 3.5, W - o - 3.5):
        for y in (o + 3.5, H - o - 3.5):
            cover.corner(c, x, y, 17)
    c.setFillColorRGB(*cover.INK); c.setFont("SerifI", 30)
    c.drawCentredString(W / 2, H - 120, "Color the Fairy Tales")
    cover.rule(c, W / 2, H - 138, 60)
    text = ("Walter Crane drew these pictures for children's books printed in London between 1873 and 1876, "
            "cut into wood and printed in color by Edmund Evans. This book brings twenty-four of them together. "
            "On the left of every spread is the plate in its original colors. On the right is the same picture "
            "as line art, ready for your own.")
    c.setFillColorRGB(*cover.INK)
    build_pdf.paragraph(c, text, 110, H - 178, W - 220, font="SerifI", size=12.5, leading=19)
    # a small spread, as it looks inside
    name = "Beautybeast00CranA-n11"
    pw = 150; ph = pw * 1.17
    y0 = H - 470
    for k, (suffix, x) in enumerate((("-color.jpg", W / 2 - pw - 6), ("-line.png", W / 2 + 6))):
        src = Image.open(f"final/{name}{suffix}"); ph = pw * src.height / src.width
        c.drawImage(jpeg(f"final/{name}{suffix}", pw, ph), x, y0, pw, ph)
        c.setStrokeColorRGB(*cover.GREEN); c.setLineWidth(0.5); c.rect(x, y0, pw, ph)
    c.setFillColorRGB(0.38, 0.35, 0.3); c.setFont("Sans", 9.5)
    stories = ["The Sleeping Beauty · Beauty and the Beast · The Frog Prince · Bluebeard",
               "Little Red Riding Hood · Goody Two Shoes · The Hind in the Wood · The Yellow Dwarf"]
    for k, line in enumerate(stories):
        c.drawCentredString(W / 2, y0 - 28 - 15 * k, line)
    # logo bottom-left; the lower right stays clear
    d = 64
    c.drawImage(ImageReader(cover.round_logo(int(d / 72 * 300))), i + 28, i + 26, d, d, mask="auto")
    c.setFillColorRGB(*cover.GREEN); c.setFont("SansB", 9)
    c.drawString(i + 28 + d + 12, i + 26 + d / 2 - 3, "thebookswanderer.com")


def make_cover(out="color-the-fairy-tales-cover.pdf"):
    c = canvas.Canvas(out, pagesize=(COVER_W, COVER_H), initialFontName="Sans")
    c.setFillColorRGB(*cover.PAPER); c.rect(0, 0, COVER_W, COVER_H, stroke=0, fill=1)
    c.saveState(); c.translate(BLEED, BLEED); back(c, TRIM_W, TRIM_H); c.restoreState()
    c.saveState(); c.translate(BLEED + TRIM_W + SPINE, BLEED)
    cover.draw_cover(c, TRIM_W, TRIM_H, paper=False, inset=36); c.restoreState()
    c.showPage(); c.save()


if __name__ == "__main__":
    build_pdf.build("color-the-fairy-tales-interior.pdf", letter, dpi=300, color_dpi=300,
                    margin=0.625 * inch, print_edition=True)
    make_cover()
