"""Assemble the Walter Crane coloring book: guide page (original colors) + page to color.

Image pages are made with img2pdf (JPEG passthrough, 1-bit CCITT G4 line art) so
the file stays small; text and captions are drawn with reportlab and merged on.
"""
import io
import img2pdf
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"
pdfmetrics.registerFont(TTFont("Serif", f"{FONTS}/Playfair-600.ttf"))
pdfmetrics.registerFont(TTFont("SerifI", f"{FONTS}/Playfair-500i.ttf"))
pdfmetrics.registerFont(TTFont("Sans", f"{FONTS}/Karla-400.ttf"))
pdfmetrics.registerFont(TTFont("SansB", f"{FONTS}/Karla-700.ttf"))
GREEN = (27 / 255, 55 / 255, 40 / 255)
GREY = (0.35, 0.35, 0.33)

BOOKS = {
    "sleepingbeauty00cran": ("The Sleeping Beauty", 1876),
    "Beautybeast00CranA": ("Beauty and the Beast", 1874),
    "frogprince00CranA": ("The Frog Prince", 1874),
    "Bluebeard00Cran": ("Bluebeard", 1873),
    "LittleRedRiding00Cran": ("Little Red Riding Hood", 1875),
    "GoodyTwoShoes00CranA": ("Goody Two Shoes", 1874),
    "hindwood00Cran": ("The Hind in the Wood", 1875),
    "yellowdwarf00Cran": ("The Yellow Dwarf", 1875),
}
ORDER = [
    "sleepingbeauty00cran-n1", "sleepingbeauty00cran-n2", "sleepingbeauty00cran-n3", "sleepingbeauty00cran-n8", "sleepingbeauty00cran-n9",
    "Beautybeast00CranA-n6", "Beautybeast00CranA-n11", "Beautybeast00CranA-n12",
    "frogprince00CranA-n6", "frogprince00CranA-n11", "frogprince00CranA-n12",
    "Bluebeard00Cran-n2", "Bluebeard00Cran-n5", "Bluebeard00Cran-n7", "Bluebeard00Cran-n10",
    "LittleRedRiding00Cran-n1", "LittleRedRiding00Cran-n5", "LittleRedRiding00Cran-n13", "LittleRedRiding00Cran-n14",
    "GoodyTwoShoes00CranA-n2", "GoodyTwoShoes00CranA-n6", "GoodyTwoShoes00CranA-n11",
    "hindwood00Cran-n2", "yellowdwarf00Cran-n12",
]
TITLE = "Color the Fairy Tales"
SUB = "24 plates by Walter Crane, 1873–1876"
M = 0.5 * inch
CAP = 0.55 * inch


def text_page(size, draw):
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=size, initialFontName="Sans"); draw(c, *size); c.showPage(); c.save()
    buf.seek(0); return PdfReader(buf).pages[0]


def image_page(size, path, line, dpi):
    """The plate fitted into the page minus margins and caption strip, top-aligned in that box."""
    W, H = size
    box_w, box_h = W - 2 * M, H - 2 * M - CAP
    im = Image.open(path)
    r = min(box_w / im.width, box_h / im.height)
    px = lambda pt: int(round(pt / 72 * dpi))
    w, h = px(im.width * r), px(im.height * r)
    canvas_px = (px(W - 2 * M), px(H - 2 * M))
    if line:
        im = im.convert("L").resize((w, h), Image.LANCZOS).point(lambda v: 255 if v > 128 else 0)
        page = Image.new("L", canvas_px, 255)
    else:
        im = im.convert("RGB").resize((w, h), Image.LANCZOS)
        page = Image.new("RGB", canvas_px, (255, 255, 255))
    page.paste(im, ((canvas_px[0] - w) // 2, (px(box_h) - h) // 2))
    buf = io.BytesIO()
    if line:
        page.convert("1").save(buf, "TIFF", compression="group4", dpi=(dpi, dpi))
    else:
        page.save(buf, "JPEG", quality=80, dpi=(dpi, dpi))
    layout = img2pdf.get_layout_fun((W, H), None, (M, M))
    return PdfReader(io.BytesIO(img2pdf.convert(buf.getvalue(), layout_fun=layout))).pages[0]


def centered(c, text, font, size, y, W, color=GREEN):
    c.setFillColorRGB(*color); c.setFont(font, size); c.drawCentredString(W / 2, y, text)


def paragraph(c, text, x, y, width, font="Sans", size=11, leading=16):
    c.setFont(font, size); c.setFillColorRGB(0.15, 0.15, 0.15)
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            t = (line + " " + word).strip()
            if c.stringWidth(t, font, size) > width:
                c.drawString(x, y, line); y -= leading; line = word
            else:
                line = t
        if line:
            c.drawString(x, y, line); y -= leading
        y -= leading * 0.6
    return y


ABOUT = (
    "Walter Crane drew these pictures for children's books printed in London between 1873 and 1876. "
    "Each one was carved into wooden blocks: one block for the black outlines and one for each color, "
    "printed one over the other by Edmund Evans.\n"
    "This book keeps that order. On the left of every spread is the plate as it was printed, with its original colors. "
    "On the right is the same plate as line art, ready to color. You can follow Crane's palette or ignore it completely.\n"
    "The verses that came with the pictures have been left out of the coloring pages, so the boxes are blank. "
    "Write in them, sign your work, or color them like the rest.\n"
    "If you print at home, print one side only on heavier paper (around 100 gsm / 28 lb) so markers don't bleed through.\n"
    "The illustrations are in the public domain. They were scanned from first editions held by Smithsonian Libraries "
    "and made available through the Internet Archive. The line art, cleaning and layout of this edition are by The Books Wanderer."
)


def build(out, size, src="final", dpi=300, color_dpi=170, margin=None, print_edition=False):
    global M
    M = margin or 0.5 * inch
    pages = []

    def title(c, W, H):
        centered(c, TITLE, "Serif", 40, H * 0.6, W)
        centered(c, SUB, "SerifI", 18, H * 0.6 - 40, W, GREY)
        centered(c, "The Books Wanderer", "SansB", 12, M + 20, W, GREY)
    import cover  # late import: cover.py imports this module for the fonts
    pages.append(text_page(size, lambda c, W, H: cover.draw_cover(c, W, H, paper=not print_edition, inset=36 if print_edition else 24)))

    def about(c, W, H):
        centered(c, "How this book works", "Serif", 24, H - M - 40, W)
        paragraph(c, ABOUT, M + 0.5 * inch, H - M - 90, W - 2 * M - inch)
    pages.append(text_page(size, about))

    def contents(c, W, H):
        centered(c, "The stories", "Serif", 24, H - M - 40, W)
        y, page = H - M - 100, 4
        seen = {}
        for name in ORDER:
            seen.setdefault(name.rsplit("-", 1)[0], page); page += 2
        for book, p in seen.items():
            story, year = BOOKS[book]
            c.setFont("SerifI", 15); c.setFillColorRGB(*GREEN); c.drawString(M + inch, y, story)
            c.setFont("Sans", 11); c.setFillColorRGB(*GREY)
            c.drawString(M + 4.2 * inch, y, str(year)); c.drawRightString(W - M - inch, y, f"page {p}")
            y -= 34
    pages.append(text_page(size, contents))

    for name in ORDER:
        story, year = BOOKS[name.rsplit("-", 1)[0]]
        left = image_page(size, f"{src}/{name}-color.jpg", False, color_dpi)
        left.merge_page(text_page(size, lambda c, W, H: (
            centered(c, story, "SerifI", 13, M + 18, W),
            centered(c, f"Walter Crane, {year} · the original colors", "Sans", 9, M + 4, W, GREY))))
        right = image_page(size, f"{src}/{name}-line.png", True, dpi)
        right.merge_page(text_page(size, lambda c, W, H: centered(c, story, "SerifI", 11, M + 10, W, GREY)))
        pages += [left, right]

    def closing(c, W, H):
        centered(c, "More to color", "Serif", 22, H * 0.6, W)
        centered(c, "thebookswanderer.com", "SansB", 13, H * 0.6 - 30, W, GREY)
    pages.append(text_page(size, closing))

    w = PdfWriter()
    for p in pages:
        w.add_page(p)
    w.add_metadata({"/Title": TITLE, "/Author": "The Books Wanderer"})
    w.compress_identical_objects()
    with open(out, "wb") as f:
        w.write(f)


if __name__ == "__main__":
    build("color-the-fairy-tales-letter.pdf", letter)
    build("color-the-fairy-tales-a4.pdf", A4)
