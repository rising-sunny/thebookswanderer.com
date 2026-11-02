"""Listing image: the four ornaments with one line of maths each (2000 x 2000 px)."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import ornaments as O

FONTS = "/tmp/claude-0/-home-user/661d7c00-130c-5805-82d8-1f86fe22eb52/scratchpad/fonts/"
S = 2000
BG, INK, SOFT = (246, 240, 228), (34, 30, 26), (110, 100, 90)
ITEMS = [
    ("koch", (178, 172, 160), "Koch snowflake, 1904",
     "Add a triangle to the middle of every edge, again and again. The edge grows without end, "
     "yet the area never passes 8/5 of the first triangle. The raised lines show steps 0, 1 and 2."),
    ("sierpinski", (30, 110, 60), "Sierpinski triangle, 1915",
     "Take out the middle triangle, then do the same in each of the three that are left. "
     "Keep going and the area shrinks to nothing while the shape stays whole."),
    ("pythagoras", (170, 36, 30), "Pythagoras tree, 1942",
     "Every square carries two smaller squares on the sides of a right triangle. "
     "Their areas always add up to the square below: a² + b² = c²."),
    ("pentaflake", (200, 150, 60), "Pentaflake",
     "A pentagon made of six pentagons, each made of six more. "
     "Every step shrinks by 1/(1 + φ), with φ the golden ratio."),
]


def font(name, size, weight=None):
    f = ImageFont.truetype(FONTS + name, size)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def wrap(d, text, f, width):
    lines, line = [], ""
    for w in text.split():
        t = (line + " " + w).strip()
        if d.textlength(t, font=f) > width and line:
            lines.append(line); line = w
        else:
            line = t
    return lines + [line]


def silhouette(name, color, box):
    m = O.mask(name)
    ys, xs = np.nonzero(m)
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h_mm, w_mm = m.shape[0] / O.PX, m.shape[1] / O.PX
    im = Image.fromarray((m * 255).astype(np.uint8))
    k = box / max(im.size)
    im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    tile = Image.new("RGBA", im.size, color + (255,)); tile.putalpha(im)
    return tile, w_mm, h_mm


def main(out="orn-card.png"):
    img = Image.new("RGB", (S, S), BG); d = ImageDraw.Draw(img)
    title, body, head, small = (font("EBGaramond.ttf", 96, 500), font("EBGaramond.ttf", 44, 420),
                                font("EBGaramond.ttf", 56, 600), font("EBGaramond-Italic.ttf", 40))
    t = "Four fractals for the tree"
    d.text((S / 2 - d.textlength(t, font=title) / 2, 110), t, font=title, fill=INK)
    for i, (name, col, h, txt) in enumerate(ITEMS):
        y = 300 + i * 405
        tile, w_mm, h_mm = silhouette(name, col, 330)
        img.paste(tile, (150 + (330 - tile.width) // 2, y + (330 - tile.height) // 2), tile)
        d.text((560, y + 10), h, font=head, fill=INK)
        yy = y + 90
        for ln in wrap(d, txt, body, 1300):
            d.text((560, yy), ln, font=body, fill=INK); yy += 58
        d.text((560, yy + 8), f"{w_mm / 10:.1f} × {h_mm / 10:.1f} cm", font=small, fill=SOFT)
    t = "Printed in PLA, about 3.5 mm thick, with a 4 mm hole for a ribbon or hook (not included)."
    d.text((S / 2 - d.textlength(t, font=small) / 2, S - 110), t, font=small, fill=SOFT)
    img.save(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
