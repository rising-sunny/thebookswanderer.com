"""Listing images for the "Christmas Time" journal (1200 x 1500, beige flat lay, same look as the Book Club Kit's).

  python build_mockups.py FRONT.png WRAP.pdf INTERIOR.pdf OUT_DIR [fonts_dir]
  # FRONT.png / WRAP.pdf come from build_journal_cover.py, INTERIOR.pdf from build_journal_interior.py (needs pdftoppm)
Writes main.jpg, open.jpg and wrap.jpg to OUT_DIR (the product folder in assets/products/).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FRONT, WRAP, INTERIOR, OUT = (Path(a) for a in sys.argv[1:5])
FONTS = Path(sys.argv[5]) if len(sys.argv) > 5 else Path(__file__).parent / "fonts"
BG, GREEN, GOLD = (231, 222, 205), (35, 63, 51), (154, 123, 60)
PAGE_EDGE = (244, 238, 224)
W, H = 1200, 1500


def font(size, italic=False):
    return ImageFont.truetype(str(FONTS / ("EBGaramond-Italic.ttf" if italic else "EBGaramond.ttf")), size)


def render(pdf, page, dpi):
    tmp = Path(tempfile.mkdtemp()) / "p"
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", "-singlefile", str(pdf), str(tmp)], check=True)
    return Image.open(str(tmp) + ".png").convert("RGB")


def shadow(canvas, box, blur=26, offset=(10, 22), alpha=95):
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]], fill=(60, 45, 30, alpha))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(blur))).convert("RGB"))


def caption(canvas, title, sub):
    d = ImageDraw.Draw(canvas)
    d.text((W / 2, H - 150), title, font=font(64), fill=GREEN, anchor="mm")
    d.text((W / 2, H - 85), sub, font=font(34, italic=True), fill=GOLD, anchor="mm")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    front = Image.open(FRONT).convert("RGB")

    # main: the closed book, a hint of page block and board thickness at the right and bottom
    im = Image.new("RGB", (W, H), BG)
    cw = 700
    cover = front.resize((cw, round(front.height * cw / front.width)), Image.LANCZOS)
    x, y = (W - cw) // 2 - 12, 150
    shadow(im, (x, y, x + cw + 22, y + cover.height + 14))
    d = ImageDraw.Draw(im)
    d.rectangle([x + 6, y + 8, x + cw + 22, y + cover.height + 14], fill=PAGE_EDGE)             # page block
    d.rectangle([x + 6, y + cover.height + 8, x + cw + 22, y + cover.height + 14], fill=(205, 195, 175))
    for k in range(0, cover.height, 6):                                                          # page lines on the fore-edge
        d.line([x + cw + 8, y + 12 + k, x + cw + 22, y + 12 + k], fill=(222, 214, 196))
    im.paste(cover, (x, y))
    d.rectangle([x, y, x + 6, y + cover.height], fill=(22, 41, 31))                              # hinge
    caption(im, "Christmas Time", "A5 hardcover journal · 120 ruled pages")
    im.save(OUT / "main.jpg", quality=88)

    # open: a spread of ruled pages
    left, right = render(INTERIOR, 4, 130), render(INTERIOR, 5, 130)
    im = Image.new("RGB", (W, H), BG)
    pw = 520
    L = left.resize((pw, round(left.height * pw / left.width)), Image.LANCZOS)
    R = right.resize((pw, L.height), Image.LANCZOS)
    x, y = (W - 2 * pw) // 2, 190
    shadow(im, (x, y, x + 2 * pw, y + L.height), blur=30, offset=(8, 26), alpha=105)
    im.paste(L, (x, y)); im.paste(R, (x + pw, y))
    g = Image.new("RGBA", im.size, (0, 0, 0, 0)); gd = ImageDraw.Draw(g)                        # gutter shading
    for k in range(60):
        a = int(70 * (1 - k / 60) ** 2)
        gd.line([x + pw - k, y, x + pw - k, y + L.height], fill=(40, 30, 20, a))
        gd.line([x + pw + k, y, x + pw + k, y + L.height], fill=(40, 30, 20, a))
    im = Image.alpha_composite(im.convert("RGBA"), g).convert("RGB")
    caption(im, "117 ruled pages", "A wider margin on the inside, for notes and quotes")
    im.save(OUT / "open.jpg", quality=88)

    # wrap: the whole cover laid flat
    wrap = render(WRAP, 1, 100)
    im = Image.new("RGB", (W, H), BG)
    ww = 1080
    wr = wrap.resize((ww, round(wrap.height * ww / wrap.width)), Image.LANCZOS)
    x, y = (W - ww) // 2, (H - wr.height) // 2 - 90
    shadow(im, (x, y, x + ww, y + wr.height), blur=28, offset=(8, 24))
    im.paste(wr, (x, y))
    caption(im, "A Victorian Christmas", "1857 wood engraving on a matte hardcover")
    im.save(OUT / "wrap.jpg", quality=88)
    print("written to", OUT)


if __name__ == "__main__":
    main()
