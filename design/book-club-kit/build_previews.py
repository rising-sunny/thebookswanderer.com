"""Listing images for The Book Club Kit (1200 x 1500, beige flat lay).

  python build_previews.py   # needs out/book-club-kit-letter.pdf and pdftoppm
Writes to assets/products/book-club-kit/.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
PDF = HERE / "out" / "book-club-kit-letter.pdf"
OUT = HERE.parents[1] / "assets" / "products" / "book-club-kit"
FONTS = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "fonts"
BG, GREEN, GOLD = (231, 222, 205), (35, 63, 51), (154, 123, 60)
W, H = 1200, 1500


def pages():
    tmp = Path(tempfile.mkdtemp())
    subprocess.run(["pdftoppm", "-r", "110", "-png", str(PDF), str(tmp / "p")], check=True)
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
    f1, f2 = font(64), font(34, italic=True)
    d.text((W / 2, H - 150), title, font=f1, fill=GREEN, anchor="mm")
    d.text((W / 2, H - 85), sub, font=f2, fill=GOLD, anchor="mm")


def new():
    return Image.new("RGB", (W, H), BG)


def main():
    P = pages()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {
        "main": ([(19, 520, (620, 120), -4), (5, 520, (90, 150), 3), (1, 600, (300, 330), 0)], "The Book Club Kit", "30 printable pages · US Letter and A4"),
        "plan": ([(5, 560, (60, 200), 2), (3, 560, (590, 160), -2)], "Plan the year", "Charter, members, calendar and nominations"),
        "vote": ([(7, 560, (60, 170), -2), (8, 560, (590, 190), 3)], "Choose the book together", "Ballots and a tally sheet"),
        "cards": ([(11, 560, (60, 170), 2), (14, 560, (590, 130), -2)], "126 question cards", "Any book, plus four genre packs"),
        "bingo": ([(19, 560, (60, 200), -3), (21, 560, (590, 160), 3)], "Four bingo cards", "Moments every book club knows"),
        "host": ([(9, 560, (60, 170), 2), (10, 560, (590, 130), -2)], "An evening, planned", "Agenda, host checklist and invitations"),
    }
    for name, (items, t, sub) in jobs.items():
        im = new()
        for n, w, xy, a in items:
            place(im, P[n], w, xy, a)
        caption(im, t, sub)
        im.save(OUT / (name + ".jpg"), quality=88)
    print("written to", OUT)


if __name__ == "__main__":
    main()
