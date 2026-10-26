"""Listing images from the renders: a quiet 'Digital render' note on each, plus a size guide."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

M = "mock/"
SERIF = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
ITALIC = "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf"
ORDER = ["hero", "studio", "underside", "parts", "rainbow"]


def note(img, text="Digital render"):
    d = ImageDraw.Draw(img, "RGBA"); f = ImageFont.truetype(ITALIC, 34)
    w = d.textlength(text, font=f)
    patch = np.asarray(img.convert("L"))[-90:, -int(w) - 80:].mean()
    col = (40, 36, 32, 170) if patch > 120 else (240, 235, 225, 170)
    d.text((img.width - w - 40, img.height - 70), text, font=f, fill=col)
    return img


def size_guide(src):
    img = Image.open(src).convert("RGB"); a = np.asarray(img).astype(int)
    bg = a[40:200, 40:200].reshape(-1, 3).mean(0)
    obj = np.abs(a - bg).sum(2) > 60
    obj[int(a.shape[0] * 0.80):] = False          # ignore the soft shadow on the floor sweep
    ys, xs = np.nonzero(obj)
    rows = obj.any(1).nonzero()[0]; top, bot = rows.min(), rows.max()
    cols_bot = np.nonzero(obj[bot - 30:bot + 1].any(0))[0]
    left, right = cols_bot.min(), cols_bot.max()
    d = ImageDraw.Draw(img); ink = (60, 52, 44); f = ImageFont.truetype(SERIF, 52)
    x = right + 90                                  # height line on the right
    d.line([(x, top), (x, bot)], fill=ink, width=4)
    for y in (top, bot):
        d.line([(x - 22, y), (x + 22, y)], fill=ink, width=4)
    d.text((x + 40, (top + bot) / 2 - 60), "10.7 cm", font=f, fill=ink)
    d.text((x + 40, (top + bot) / 2 + 4), "4.2 in", font=f, fill=ink)
    y = bot + 90                                    # base width underneath
    d.line([(left, y), (right, y)], fill=ink, width=4)
    for xx in (left, right):
        d.line([(xx, y - 22), (xx, y + 22)], fill=ink, width=4)
    t = "8.2 cm  ·  3.2 in"; w = d.textlength(t, font=f)
    d.text(((left + right) / 2 - w / 2, y + 30), t, font=f, fill=ink)
    return img


if __name__ == "__main__":
    for i, s in enumerate(ORDER, 1):
        note(Image.open(M + s + ".png").convert("RGB")).save(M + f"{i:02d}-{s}.jpg", quality=92)
    note(size_guide(M + "studio.png")).save(M + "06-size.jpg", quality=92)
    print("ok")
