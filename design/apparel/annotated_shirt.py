"""Sweatshirt print v2: only the first paragraph, heavier type and bigger marks so it reads on fabric
from a few steps away. Same fonts and helpers as annotated_page.py. 3600 x 4300 px, transparent.
"""
import math
from PIL import Image, ImageDraw
from annotated_page import font, layout, span, wobbly, TEXT, W, H

INK = (30, 26, 22, 255)
PEN, RED = (28, 56, 122, 255), (172, 34, 26, 255)
YELLOW, PINK = (255, 210, 64, 255), (255, 146, 194, 255)
LW = 15                                             # pen width


def main(out="shirt.png"):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    marks = Image.new("RGBA", (W, H), (0, 0, 0, 0)); md = ImageDraw.Draw(marks)
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0)); td = ImageDraw.Draw(text)
    body = font("EBGaramond.ttf", 150, 540)
    caps = font("EBGaramond.ttf", 120, 600)
    hand = font("Caveat.ttf", 200, 620)
    hand_s = font("Caveat.ttf", 168, 600)

    x0, x1 = 300, W - 1180
    t = "CHAPTER I."
    td.text(((x0 + x1) / 2 - td.textlength(t, font=caps) / 2, 330), t, font=caps, fill=INK)
    boxes, y_end = layout(td, TEXT.split(" "), x0, x1, 680, body, 240, justify=False)
    for w, bx, by, _ in boxes:
        td.text((bx, by), w, font=body, fill=INK)
    line = lambda word: next(y for w, _x, y, _b in boxes if w.startswith(word))

    for (a, y, b) in span(boxes, 2, 4, body):
        md.rounded_rectangle([a - 16, y + 26, b + 20, y + 196], radius=28, fill=YELLOW)
    for (a, y, b) in span(boxes, 18, 5, body):
        md.rounded_rectangle([a - 16, y + 26, b + 20, y + 196], radius=28, fill=PINK)
    for (a, y, b) in span(boxes, 7, 9, body):
        wobbly(md, [(x, y + 212 + 11 * math.sin(x / 40)) for x in range(int(a), int(b), 12)], PEN, LW)
    i = next(k for k, (w, *_r) in enumerate(boxes) if w.startswith("property"))
    _, bx, by, bx1 = boxes[i]
    cx, cy, rx, ry = (bx + bx1) / 2, by + 108, (bx1 - bx) / 2 + 50, 120
    wobbly(md, [(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in [k * 0.12 - 0.4 for k in range(60)]], RED, LW)

    def note(x, y, s, f=hand, fill=PEN, angle=0):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        ld.text((x, y), s, font=f, fill=fill, spacing=-10)
        if angle:
            layer = layer.rotate(angle, center=(x, y), resample=Image.BICUBIC)
        marks.alpha_composite(layer)
    nx = x1 + 110
    note(nx, line("It") - 40, "the most\nfamous first\nline ever", angle=4)
    yw = line("wife.")
    note(nx + 40, yw + 40, "irony!!", fill=RED, angle=-6)
    wobbly(md, [(nx + 30, yw + 150), (nx - 30, yw + 172), (nx - 70, yw + 165)], RED, LW - 3)
    note(nx, line("neighbourhood,") - 20, "rich + single\n= trouble", f=hand_s, angle=5)
    note(nx, line("property") + 10, "poor guy,\nno say in it", f=hand_s, fill=RED, angle=-4)

    yf = y_end + 150
    note(x0, yf, "reread #4", f=hand_s, angle=-1.5)
    hx, hy = x0 + 720, yf + 95
    wobbly(md, [(hx + 56 * math.sin(t) ** 3, hy - (45 * math.cos(t) - 18 * math.cos(2 * t) - 7 * math.cos(3 * t) - 2.5 * math.cos(4 * t)))
                for t in [k * 0.1 for k in range(64)]], RED, LW - 2)
    note(x0 + 860, yf, "still the best opening in English", f=hand_s, angle=-1.5)
    note(x1 - 380, yf + 260, "— J. A., 1813", f=hand, fill=INK)

    img.alpha_composite(marks); img.alpha_composite(text)
    img.save(out)
    return img


if __name__ == "__main__":
    im = main()
    print(im.size, im.getchannel("A").getbbox())
    for name, col in (("sand", (214, 197, 170)), ("pink", (246, 210, 222))):
        bg = Image.new("RGBA", im.size, col + (255,)); bg.alpha_composite(im)
        bg.convert("RGB").resize((W // 4, H // 4), Image.LANCZOS).save(f"shirt-{name}.jpg", quality=88)
