"""Listing images for the 2027 Reading Challenge Kit (1200 x 1500, beige flat lay).

  python build_previews.py   # needs out/reading-challenge-kit-2027-letter.pdf and pdftoppm
Writes to assets/products/reading-challenge-kit-2027/.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
PDF = HERE / "out" / "reading-challenge-kit-2027-letter.pdf"
OUT = HERE.parents[1] / "assets" / "products" / "reading-challenge-kit-2027"
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

    im = new()                                                   # 1. hero
    place(im, P[6], 520, (620, 120), -4)
    place(im, P[5], 520, (90, 150), 3)
    place(im, P[1], 600, (300, 330))
    caption(im, "2027 Reading Challenge Kit", "27 printable pages · US Letter and A4")
    im.save(OUT / "main.jpg", quality=88)

    im = new()                                                   # 2. what's inside
    picks = [1, 4, 5, 6, 10, 22, 24, 26, 27]
    tw = 330
    for i, n in enumerate(picks):
        r, c = divmod(i, 3)
        place(im, P[n], tw, (60 + c * (tw + 45), 50 + r * 450))
    im = im.crop((0, 0, W, H))
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 140, W, H], fill=BG)
    d.text((W / 2, H - 80), "What's inside: tracker, bingo, monthly logs, reviews", font=font(40), fill=GREEN, anchor="mm")
    im.save(OUT / "inside.jpg", quality=88)

    im = new()                                                   # 3. bookshelf tracker
    place(im, P[5], 900, (150, 90))
    caption(im, "Colour one spine per book", "52 numbered spines, one for each prompt")
    im.save(OUT / "shelf.jpg", quality=88)

    im = new()                                                   # 4. bingo
    place(im, P[7], 560, (60, 200), -3)
    place(im, P[6], 560, (590, 160), 3)
    caption(im, "Four bingo cards", "Play with friends or a book club")
    im.save(OUT / "bingo.jpg", quality=88)

    im = new()                                                   # 5. monthly + reviews
    place(im, P[22], 560, (60, 170), 2)
    place(im, P[10], 560, (580, 130), -2)
    caption(im, "A page for every month", "Titles, pages, stars and the line worth keeping")
    im.save(OUT / "monthly.jpg", quality=88)

    im = new()                                                   # 6. year in books + TBR
    place(im, P[27], 560, (590, 160), -2)
    place(im, P[3], 560, (60, 200), 2)
    caption(im, "Plan it, then look back", "Goals for January, the year in books in December")
    im.save(OUT / "year.jpg", quality=88)
    print("written to", OUT)


if __name__ == "__main__":
    main()
