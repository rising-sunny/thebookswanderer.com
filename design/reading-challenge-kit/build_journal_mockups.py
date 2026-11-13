"""Listing images for the 2027 Reading Challenge Journal (1200 x 1500, beige flat lay like the other kits').

  python build_journal_mockups.py COVER.pdf INTERIOR.pdf OUT_DIR FONTS_DIR     # needs pdftoppm
Writes main.jpg, open.jpg, pages.jpg and wrap.jpg.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

COVER, INTERIOR, OUT, FONTS = (Path(a) for a in sys.argv[1:5])
BG, GREEN, GOLD, PAGE_EDGE = (231, 222, 205), (35, 63, 51), (154, 123, 60), (244, 238, 224)
W, H = 1200, 1500


def font(size, italic=False):
    return ImageFont.truetype(str(FONTS / ("EBGaramond-Italic.ttf" if italic else "EBGaramond.ttf")), size)


def render(pdf, page, dpi):
    tmp = Path(tempfile.mkdtemp()) / "p"
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", "-singlefile", str(pdf), str(tmp)], check=True)
    return Image.open(str(tmp) + ".png").convert("RGB")


def shadow(canvas, box, blur=24, offset=(8, 22), alpha=95):
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]], fill=(60, 45, 30, alpha))
    return Image.alpha_composite(canvas.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(blur))).convert("RGB")


def caption(img, title, sub):
    d = ImageDraw.Draw(img)
    d.text((W / 2, H - 150), title, font=font(64), fill=GREEN, anchor="mm")
    d.text((W / 2, H - 85), sub, font=font(34, italic=True), fill=GOLD, anchor="mm")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cover = render(COVER, 1, 300)
    bleed, trim_w, trim_h, spine = 8.78, 5.83 * 72, 8.27 * 72, 13.92
    s = 300 / 72
    front = cover.crop((round((bleed + trim_w + spine) * s), round(bleed * s), round((bleed + 2 * trim_w + spine) * s), round((bleed + trim_h) * s)))

    # main: the closed book with a page-block edge
    im = Image.new("RGB", (W, H), BG)
    cw = 700
    cv = front.resize((cw, round(front.height * cw / front.width)), Image.LANCZOS)
    x, y = (W - cw) // 2 - 10, 150
    im = shadow(im, (x, y, x + cw + 14, y + cv.height + 10)); d = ImageDraw.Draw(im)
    d.rectangle([x + 6, y + 6, x + cw + 14, y + cv.height + 10], fill=PAGE_EDGE)
    im.paste(cv, (x, y)); d.rectangle([x, y, x + 5, y + cv.height], fill=(18, 34, 24))
    caption(im, "The 2027 Reading Challenge Journal", "A5 paperback · 56 pages · full colour")
    im.save(OUT / "main.jpg", quality=88)

    # open: two facing pages (the bookshelf tracker and bingo card A)
    left, right = render(INTERIOR, 7, 130), render(INTERIOR, 8, 130)
    im = Image.new("RGB", (W, H), BG); pw = 520
    L = left.resize((pw, round(left.height * pw / left.width)), Image.LANCZOS); R = right.resize((pw, L.height), Image.LANCZOS)
    x, y = (W - 2 * pw) // 2, 190
    im = shadow(im, (x, y, x + 2 * pw, y + L.height), blur=30, offset=(8, 26), alpha=105)
    im.paste(L, (x, y)); im.paste(R, (x + pw, y))
    g = Image.new("RGBA", im.size, (0, 0, 0, 0)); gd = ImageDraw.Draw(g)
    for k in range(60):
        a = int(70 * (1 - k / 60) ** 2)
        gd.line([x + pw - k, y, x + pw - k, y + L.height], fill=(40, 30, 20, a)); gd.line([x + pw + k, y, x + pw + k, y + L.height], fill=(40, 30, 20, a))
    im = Image.alpha_composite(im.convert("RGBA"), g).convert("RGB")
    caption(im, "A shelf to colour, a bingo to play", "Colour one spine for every book you finish")
    im.save(OUT / "open.jpg", quality=88)

    # pages: six inside pages
    im = Image.new("RGB", (W, H), BG)
    pages = [5, 12, 24, 52, 53, 50]
    tw = 340
    for i, pg in enumerate(pages):
        p = render(INTERIOR, pg, 90); p = p.resize((tw, round(p.height * tw / p.width)), Image.LANCZOS)
        cx, cy = 70 + (i % 3) * (tw + 25), 130 + (i // 3) * (p.height + 30)
        im = shadow(im, (cx, cy, cx + tw, cy + p.height), blur=14, offset=(4, 10), alpha=80); im.paste(p, (cx, cy))
    caption(im, "Everything for the year", "Checklist, monthly logs, reviews, lists and a year in books")
    im.save(OUT / "pages.jpg", quality=88)

    # wrap: the whole cover laid flat
    im = Image.new("RGB", (W, H), BG)
    ww = 1080; wr = cover.resize((ww, round(cover.height * ww / cover.width)), Image.LANCZOS)
    x, y = (W - ww) // 2, (H - wr.height) // 2 - 90
    im = shadow(im, (x, y, x + ww, y + wr.height), blur=26, offset=(8, 24)); im.paste(wr, (x, y))
    caption(im, "A year of reading", "One book a week, none of them assigned")
    im.save(OUT / "wrap.jpg", quality=88)
    print("written to", OUT)


if __name__ == "__main__":
    main()
