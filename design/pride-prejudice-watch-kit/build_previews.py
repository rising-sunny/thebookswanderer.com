"""Listing images for the Pride and Prejudice Watch-Along & Read-Along Kit (1200 x 1500, beige flat lay).

  python build_previews.py <fonts_dir>   # needs out/pride-prejudice-watch-kit-letter.pdf and pdftoppm
Writes to assets/products/pride-prejudice-watch-party-kit/.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
PDF = HERE / "out" / "pride-prejudice-watch-kit-letter.pdf"
OUT = HERE.parents[1] / "assets" / "products" / "pride-prejudice-watch-party-kit"
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


def caption(canvas, title, sub, size=60):
    d = ImageDraw.Draw(canvas)
    d.text((W / 2, H - 150), title, font=font(size), fill=GREEN, anchor="mm")
    d.text((W / 2, H - 85), sub, font=font(34, italic=True), fill=GOLD, anchor="mm")


def new():
    return Image.new("RGB", (W, H), BG)


def main():
    P = pages()
    OUT.mkdir(parents=True, exist_ok=True)

    im = new()                                                   # 1. hero
    place(im, P[8], 520, (620, 120), -4)
    place(im, P[3], 520, (90, 150), 3)
    place(im, P[1], 600, (300, 330))
    caption(im, "Watch-Along & Read-Along Kit", "Pride and Prejudice  ·  18 printable pages  ·  Letter and A4", 56)
    im.save(OUT / "main.jpg", quality=88)

    im = new()                                                   # 2. what's inside
    picks = [1, 3, 4, 6, 7, 11, 12, 14, 15]
    tw = 330
    for i, n in enumerate(picks):
        r, c = divmod(i, 3)
        place(im, P[n], tw, (60 + c * (tw + 45), 50 + r * 450))
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 140, W, H], fill=BG)
    d.text((W / 2, H - 80), "What's inside: plan, episode notes, bingo, quotes, party", font=font(38), fill=GREEN, anchor="mm")
    im.save(OUT / "inside.jpg", quality=88)

    im = new()                                                   # 3. reading plan
    place(im, P[3], 900, (150, 90))
    caption(im, "Nine weeks, sixty-one chapters", "A reading plan with what to look out for each week")
    im.save(OUT / "plan.jpg", quality=88)

    im = new()                                                   # 4. bingo
    place(im, P[8], 560, (60, 200), -3)
    place(im, P[7], 560, (590, 160), 3)
    caption(im, "Four bingo cards", "Moments from the book to spot on screen")
    im.save(OUT / "bingo.jpg", quality=88)

    im = new()                                                   # 5. quotes + first line card
    place(im, P[11], 560, (60, 170), 2)
    place(im, P[17], 560, (590, 220), -2)
    caption(im, "Lines to listen for", "Twelve sentences from the novel, and a first line to frame")
    im.save(OUT / "quotes.jpg", quality=88)

    im = new()                                                   # 6. party
    place(im, P[14], 560, (60, 190), -2)
    place(im, P[15], 560, (590, 150), 2)
    caption(im, "Host a watch party", "A planning page and twelve questions for the sofa")
    im.save(OUT / "party.jpg", quality=88)
    print("written to", OUT)


if __name__ == "__main__":
    main()
