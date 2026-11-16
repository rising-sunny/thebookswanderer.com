"""Listing images for The Reader's Memory Journal (1200 x 1500, beige flat lay), EN and ES.

  python build_previews.py FONTS_DIR PDF_DIR OUT_DIR     # needs pdftoppm and the PDFs from build_memory_journal.py
Writes main_{en,es}.jpg, inside_{en,es}.jpg, memory_{en,es}.jpg and letters_{en,es}.jpg to OUT_DIR
(normally assets/products/readers-memory-journal/).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(sys.argv[1])
PDFS = Path(sys.argv[2])
OUT = Path(sys.argv[3])
BG, GREEN, GOLD = (231, 222, 205), (35, 63, 51), (154, 123, 60)
W, H = 1200, 1500
# page numbers in the PDF
COVER, OWNER, HOWTO, LIFE, PLACES, MEMORY, QUOTES, LETTER, LETTER_AUTHOR, GIFTS, CHANGED, YEAR = 1, 2, 3, 4, 5, 6, 24, 26, 27, 29, 30, 32
CAPTIONS = {
    "en": {"main": ("The Reader's Memory Journal", "32 printable pages · US Letter and A4"),
           "inside": ("What's inside", "Book memories, quotes, letters, lists and a year in memories"),
           "memory": ("A page for every book", "Where you were, who you were with, how it felt"),
           "letters": ("Letters and lines to keep", "To a character, to an author, to your younger self")},
    "es": {"main": ("El diario de memorias lectoras", "32 páginas imprimibles · Carta y A4"),
           "inside": ("Qué incluye", "Memorias de libros, citas, cartas, listas y un año en memorias"),
           "memory": ("Una página para cada libro", "Dónde estabas, con quién, cómo se sintió"),
           "letters": ("Cartas y frases para guardar", "A un personaje, a un autor, a tu yo más joven")},
}
NAMES = {"en": "readers-memory-journal", "es": "diario-de-memorias-lectoras"}


def pages(pdf):
    tmp = Path(tempfile.mkdtemp())
    subprocess.run(["pdftoppm", "-r", "110", "-png", str(pdf), str(tmp / "p")], check=True)
    return {int(p.stem.split("-")[1]): Image.open(p).convert("RGB") for p in sorted(tmp.glob("p-*.png"))}


def font(size, italic=False):
    return ImageFont.truetype(str(FONTS / ("EBGaramond-Italic.ttf" if italic else "EBGaramond.ttf")), size)


def place(canvas, page, width, xy, angle=0):
    p = page.resize((width, int(page.height * width / page.width)), Image.LANCZOS)
    if angle:
        p = p.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=BG)
    shadow = Image.new("RGBA", (p.width + 60, p.height + 60), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([30, 34, 30 + p.width, 34 + p.height], fill=(60, 45, 30, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    canvas.paste(shadow, (xy[0] - 30, xy[1] - 30), shadow)
    canvas.paste(p, xy)


def caption(canvas, title, sub):
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, H - 190, W, H], fill=BG)
    d.text((W / 2, H - 125), title, font=font(60), fill=GREEN, anchor="mm")
    d.text((W / 2, H - 62), sub, font=font(32, italic=True), fill=GOLD, anchor="mm")


def make(lang):
    P = pages(PDFS / f"{NAMES[lang]}-letter.pdf")
    cap = CAPTIONS[lang]
    OUT.mkdir(parents=True, exist_ok=True)

    im = Image.new("RGB", (W, H), BG)                              # 1. hero
    place(im, P[LIFE], 500, (650, 150), 3)
    place(im, P[MEMORY], 520, (40, 190), -3)
    place(im, P[COVER], 640, (280, 430))
    caption(im, *cap["main"]); im.save(OUT / f"main_{lang}.jpg", quality=88)

    im = Image.new("RGB", (W, H), BG)                              # 2. what's inside
    picks = [OWNER, PLACES, MEMORY, QUOTES, LETTER, GIFTS, CHANGED, YEAR, HOWTO]
    tw = 330
    for i, n in enumerate(picks):
        r, c = divmod(i, 3)
        place(im, P[n], tw, (60 + c * (tw + 45), 40 + r * 440))
    caption(im, *cap["inside"]); im.save(OUT / f"inside_{lang}.jpg", quality=88)

    im = Image.new("RGB", (W, H), BG)                              # 3. the book memory page
    place(im, P[MEMORY], 880, (160, 70))
    caption(im, *cap["memory"]); im.save(OUT / f"memory_{lang}.jpg", quality=88)

    im = Image.new("RGB", (W, H), BG)                              # 4. letters and quotes
    place(im, P[QUOTES], 560, (50, 330), -2)
    place(im, P[LETTER_AUTHOR], 560, (600, 290), 2)
    caption(im, *cap["letters"]); im.save(OUT / f"letters_{lang}.jpg", quality=88)


if __name__ == "__main__":
    for lang in ("en", "es"):
        make(lang)
    print("written to", OUT)
