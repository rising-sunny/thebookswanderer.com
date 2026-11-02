"""Mug wrap of the annotated Pride and Prejudice page: an open book, two pages across the wrap.
Same fonts, colours and marks as annotated_page.py. 2700 x 1050 px = 9 x 3.5 in at 300 dpi.
"""
import math
from PIL import Image, ImageDraw, ImageFilter
from annotated_page import font, layout, span, wobbly, PAPER, INK, PEN, RED, YELLOW, PINK

W, H = 2700, 1050
LEFT = ("It is a truth universally acknowledged, that a single man in possession of a good fortune, "
        "must be in want of a wife.")
RIGHT = ("\u201cMy dear Mr. Bennet,\u201d said his lady to him one day, \u201chave you heard that "
         "Netherfield Park is let at last?\u201d")


def main(out="mug.png"):
    img = Image.new("RGBA", (W, H), PAPER)
    # the gutter: a soft shadow down the middle, so the wrap reads as an open book
    shade = Image.new("L", (W, H), 0); sd = ImageDraw.Draw(shade)
    sd.rectangle([W // 2 - 40, 0, W // 2 + 40, H], fill=70)
    shade = shade.filter(ImageFilter.GaussianBlur(45))
    img = Image.composite(Image.new("RGBA", (W, H), (150, 128, 96, 255)), img, shade)
    marks = Image.new("RGBA", (W, H), (0, 0, 0, 0)); md = ImageDraw.Draw(marks)
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0)); td = ImageDraw.Draw(text)

    body = font("EBGaramond.ttf", 74, 430)
    caps = font("EBGaramond.ttf", 58, 500)
    hand = font("Caveat.ttf", 82, 560)
    hand_s = font("Caveat.ttf", 66, 520)

    # left page
    lx0, lx1 = 170, W // 2 - 330
    t = "CHAPTER I."
    td.text(((lx0 + lx1) / 2 - td.textlength(t, font=caps) / 2, 150), t, font=caps, fill=INK)
    lb, ly = layout(td, LEFT.split(" "), lx0, lx1, 300, body, 122)
    for (a, y, b) in span(lb, 2, 4, body):
        md.rounded_rectangle([a - 8, y + 12, b + 10, y + 96], radius=14, fill=YELLOW)
    for (a, y, b) in span(lb, 7, 9, body):
        wobbly(md, [(x, y + 102 + 5 * math.sin(x / 22)) for x in range(int(a), int(b), 8)], PEN, 6)
    for (a, y, b) in span(lb, 18, 5, body):
        md.rounded_rectangle([a - 8, y + 12, b + 10, y + 96], radius=14, fill=PINK)
    # right page
    rx0, rx1 = W // 2 + 150, W - 380
    rb, ry = layout(td, RIGHT.split(" "), rx0, rx1, 300, body, 122)
    # a bracket in pen beside Mrs Bennet's line, and "Netherfield" circled
    yb0, yb1 = rb[0][2] + 15, rb[-1][2] + 105
    wobbly(md, [(rx0 - 40, yb0), (rx0 - 60, yb0 + 12), (rx0 - 60, yb1 - 12), (rx0 - 40, yb1)], PEN, 6)
    i = next(k for k, (w, *_r) in enumerate(rb) if w.startswith("Netherfield"))
    _, bx, by, bx1 = rb[i]
    cx, cy, rx, rr = (bx + bx1) / 2, by + 54, (bx1 - bx) / 2 + 26, 58
    wobbly(md, [(cx + rx * math.cos(a), cy + rr * math.sin(a)) for a in [k * 0.12 - 0.4 for k in range(60)]], RED, 6)
    for w, x, y, _ in lb + rb:
        td.text((x, y), w, font=body, fill=INK)

    def note(x, y, s, f=hand, fill=PEN, angle=0):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        ld.text((x, y), s, font=f, fill=fill)
        if angle:
            layer = layer.rotate(angle, center=(x, y), resample=Image.BICUBIC)
        marks.alpha_composite(layer)
    note(lx1 + 40, 280, "the most\nfamous first\nline ever", angle=4)
    note(lx1 + 60, 620, "irony!!", fill=RED, angle=-6)
    note(lx0, ly + 40, "reread #4", f=hand_s, angle=-1.5)
    hx, hy = lx0 + 330, ly + 85
    wobbly(md, [(hx + 26 * math.sin(t) ** 3, hy - (21 * math.cos(t) - 8 * math.cos(2 * t) - 3 * math.cos(3 * t) - math.cos(4 * t)))
                for t in [k * 0.1 for k in range(64)]], RED, 6)
    note(rx1 + 40, 290, "Mrs. Bennet\nenergy", f=hand_s, angle=4)
    note(rx1 + 40, by + 120, "the plot\nbegins!", f=hand_s, fill=RED, angle=-4)
    note(rx0 + 380, ry + 30, "— J. A., 1813", f=hand, fill=INK)

    img.alpha_composite(marks); img.alpha_composite(text)
    img.save(out)
    return img


if __name__ == "__main__":
    im = main()
    im.resize((W // 3, H // 3), Image.LANCZOS).save("mug-preview.png")
    print("mug.png", im.size)
