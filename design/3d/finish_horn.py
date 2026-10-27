"""Listing images for Gabriel's horn: 'Digital render' on each, and a size guide on the studio view."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from finish import note, SERIF

M = "mock/"; OUT = M + "horn-final/"
PAIRS = [("horn-rainbow", "main"), ("horn-gold", "gold"), ("horn-desk", "desk"), ("horn-top", "ring"), ("horn-tunnel", "tunnel")]


def size_guide(src):
    img = Image.open(src).convert("RGB"); a = np.asarray(img).astype(int)
    bg = a[40:200, 40:200].reshape(-1, 3).mean(0)
    obj = np.abs(a - bg).sum(2) > 60
    obj[int(a.shape[0] * 0.85):] = False
    rows = obj.any(1).nonzero()[0]; top, bot = rows.min(), rows.max()
    band = obj[bot - (bot - top) // 4:bot + 1]                  # the plinth: widest part near the bottom
    cols = np.nonzero(band.any(0))[0]; left, right = cols.min(), cols.max()
    d = ImageDraw.Draw(img); ink = (60, 52, 44); f = ImageFont.truetype(SERIF, 52)
    x = right + 90
    d.line([(x, top), (x, bot)], fill=ink, width=4)
    for y in (top, bot):
        d.line([(x - 22, y), (x + 22, y)], fill=ink, width=4)
    d.text((x + 40, (top + bot) / 2 - 60), "10.2 cm", font=f, fill=ink)
    d.text((x + 40, (top + bot) / 2 + 4), "4 in", font=f, fill=ink)
    y = bot + 90
    d.line([(left, y), (right, y)], fill=ink, width=4)
    for xx in (left, right):
        d.line([(xx, y - 22), (xx, y + 22)], fill=ink, width=4)
    t = "10.4 cm  ·  4.1 in"; w = d.textlength(t, font=f)
    d.text(((left + right) / 2 - w / 2, y + 30), t, font=f, fill=ink)
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for src, dst in PAIRS:
        note(Image.open(M + src + ".png").convert("RGB")).resize((1400, 1400), Image.LANCZOS).save(OUT + dst + ".jpg", quality=86, optimize=True, progressive=True)
    note(size_guide(M + "horn-rainbow.png")).resize((1400, 1400), Image.LANCZOS).save(OUT + "size.jpg", quality=86, optimize=True, progressive=True)
    print(sorted(os.listdir(OUT)))
