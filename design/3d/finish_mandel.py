"""Listing images for the Mandelbrot mountain: 'Digital render' on each, and a size guide on the top view."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from finish import note, SERIF

M = "mock/"
OUT = M + "mandel-final/"
PAIRS = [("mandel-hero", "main"), ("mandel-desk", "desk"), ("mandel-top", "top"), ("mandel-under", "equation"),
         ("mandel-sunset", "sunset")]


def size_guide(src):
    img = Image.open(src).convert("RGB"); a = np.asarray(img).astype(int)
    bg = a[40:200, 40:200].reshape(-1, 3).mean(0)
    obj = np.abs(a - bg).sum(2) > 70
    rows, cols = obj.any(1).nonzero()[0], obj.any(0).nonzero()[0]
    top, bot, left, right = rows.min(), rows.max(), cols.min(), cols.max()
    d = ImageDraw.Draw(img); ink = (60, 52, 44); f = ImageFont.truetype(SERIF, 52)
    y = bot + 80
    d.line([(left, y), (right, y)], fill=ink, width=4)
    for x in (left, right):
        d.line([(x, y - 22), (x, y + 22)], fill=ink, width=4)
    t = "11.2 cm  ·  4.4 in"; w = d.textlength(t, font=f)
    d.text(((left + right) / 2 - w / 2, y + 28), t, font=f, fill=ink)
    x = right + 80
    d.line([(x, top), (x, bot)], fill=ink, width=4)
    for yy in (top, bot):
        d.line([(x - 22, yy), (x + 22, yy)], fill=ink, width=4)
    d.text((x + 34, (top + bot) / 2 - 60), "8.4 cm", font=f, fill=ink)
    d.text((x + 34, (top + bot) / 2 + 4), "3.3 in", font=f, fill=ink)
    t = "2.8 cm (1.1 in) tall at the summit"; w = d.textlength(t, font=f)
    d.text(((left + right) / 2 - w / 2, top - 120), t, font=f, fill=ink)
    return img


if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    for src, dst in PAIRS:
        if os.path.exists(M + src + ".png"):
            note(Image.open(M + src + ".png").convert("RGB")).resize((1400, 1400), Image.LANCZOS).save(OUT + dst + ".jpg", quality=86, optimize=True, progressive=True)
    note(size_guide(M + "mandel-top.png")).resize((1400, 1400), Image.LANCZOS).save(OUT + "size.jpg", quality=86, optimize=True, progressive=True)
    print(sorted(os.listdir(OUT)))
