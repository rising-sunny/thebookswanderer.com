"""'Annotated' artwork: the first lines of Pride and Prejudice (1813, public domain) as a page
someone has read with a highlighter and a pen. Fonts: EB Garamond and Caveat (SIL OFL 1.1).

  python annotated_page.py            # page.png (print file, transparent around the page)
"""
import math
import random
from PIL import Image, ImageDraw, ImageFont

F = "/tmp/claude-0/-home-user/661d7c00-130c-5805-82d8-1f86fe22eb52/scratchpad/fonts/"
W, H = 3600, 4300                       # 12 x 14.3 in at 300 dpi
PAPER, INK = (246, 238, 220, 255), (34, 30, 26, 255)
PEN, RED = (38, 70, 130, 235), (176, 42, 32, 235)
YELLOW, PINK = (255, 222, 60, 120), (255, 120, 170, 105)

TEXT = ("It is a truth universally acknowledged, that a single man in possession of a good fortune, "
        "must be in want of a wife. However little known the feelings or views of such a man may be "
        "on his first entering a neighbourhood, this truth is so well fixed in the minds of the "
        "surrounding families, that he is considered as the rightful property of some one or other "
        "of their daughters.")
TEXT2 = ("\u201cMy dear Mr. Bennet,\u201d said his lady to him one day, \u201chave you heard that "
         "Netherfield Park is let at last?\u201d")


def font(name, size, weight=None):
    f = ImageFont.truetype(F + name, size)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def layout(draw, words, x0, x1, y0, f, lead, justify=True):
    """Justified lines; returns each word's box so the marks can find their words."""
    space = draw.textlength(" ", font=f)
    lines, line = [], []
    for w in words:
        trial = line + [w]
        if draw.textlength(" ".join(trial), font=f) > x1 - x0 and line:
            lines.append(line); line = [w]
        else:
            line = trial
    lines.append(line)
    boxes, y = [], y0
    for i, ln in enumerate(lines):
        widths = [draw.textlength(w, font=f) for w in ln]
        gap = space if not justify or i == len(lines) - 1 or len(ln) == 1 else (x1 - x0 - sum(widths)) / (len(ln) - 1)
        x = x0
        for w, wd in zip(ln, widths):
            boxes.append((w, x, y, x + wd))
            x += wd + gap
        y += lead
    return boxes, y


def span(boxes, start, n, f):
    """The words from index start to start + n - 1, as (x0, y, x1) per line."""
    segs = {}
    for w, x0, y, x1 in boxes[start:start + n]:
        a = segs.setdefault(y, [x0, x1]); a[0] = min(a[0], x0); a[1] = max(a[1], x1)
    return [(a[0], y, a[1]) for y, a in sorted(segs.items())]


def wobbly(draw, pts, fill, width):
    draw.line(pts, fill=fill, width=width, joint="curve")


def main(out="page.png", seed=3, with_paper=True):
    random.seed(seed)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    paper = Image.new("RGBA", (W, H), (0, 0, 0, 0)); pd = ImageDraw.Draw(paper)
    if with_paper:
        pd.rectangle([60, 60, W - 60, H - 60], fill=PAPER)
    marks = Image.new("RGBA", (W, H), (0, 0, 0, 0)); md = ImageDraw.Draw(marks)
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0)); td = ImageDraw.Draw(text)

    body = font("EBGaramond.ttf", 132, 430)
    caps = font("EBGaramond.ttf", 104, 500)
    hand = font("Caveat.ttf", 150, 560)
    hand_s = font("Caveat.ttf", 118, 520)

    x0, x1 = 470, W - 980                # wide right margin for the notes
    t = "CHAPTER I."
    td.text(((x0 + x1) / 2 - td.textlength(t, font=caps) / 2, 420), t, font=caps, fill=INK)
    words = TEXT.split(" ")
    boxes, y_end = layout(td, words, x0, x1, 760, body, 214)
    boxes2, y_end = layout(td, TEXT2.split(" "), x0 + 120, x1, y_end + 110, body, 214)
    for w, bx, by, _ in boxes + boxes2:
        td.text((bx, by), w, font=body, fill=INK)
    # pen: a bracket beside Mrs Bennet's line, and a note
    yb0, yb1 = boxes2[0][2] + 30, boxes2[-1][2] + 180
    wobbly(md, [(x0 + 70, yb0), (x0 + 40, yb0 + 20), (x0 + 40, yb1 - 20), (x0 + 70, yb1)], PEN, 9)

    # highlighter: "a truth universally acknowledged," (words 3..6) and "in want of a wife." (12..16)
    for (a, y, b) in span(boxes, 2, 4, body):
        md.rounded_rectangle([a - 14, y + 22, b + 18, y + 170], radius=24, fill=YELLOW)
    for (a, y, b) in span(boxes, 18, 5, body):
        md.rounded_rectangle([a - 14, y + 22, b + 18, y + 170], radius=24, fill=PINK)
    # pen: wavy underline under "a single man in possession of a good fortune,"
    for (a, y, b) in span(boxes, 7, 9, body):
        pts = [(x, y + 182 + 9 * math.sin(x / 38)) for x in range(int(a), int(b), 12)]
        wobbly(md, pts, PEN, 9)
    # pen: circle round "property"
    i = next(k for k, (w, *_r) in enumerate(boxes) if w.startswith("property"))
    _, bx, by, bx1 = boxes[i]
    cx, cy, rx, ry = (bx + bx1) / 2, by + 95, (bx1 - bx) / 2 + 46, 105
    pts = [(cx + rx * math.cos(a) + random.uniform(-4, 4), cy + ry * math.sin(a) + random.uniform(-4, 4))
           for a in [k * 0.12 - 0.4 for k in range(60)]]
    wobbly(md, pts, RED, 10)

    # margin notes in the right margin and below the text
    def note(x, y, s, f=hand, fill=PEN, angle=0):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        ld.text((x, y), s, font=f, fill=fill)
        if angle:
            layer = layer.rotate(angle, center=(x, y), resample=Image.BICUBIC)
        marks.alpha_composite(layer)
    note(x1 + 90, 740, "the most\nfamous first\nline ever", angle=4)
    note(x1 + 110, 1250, "irony!!", fill=RED, angle=-6)
    wobbly(md, [(x1 + 100, 1330), (x1 + 20, 1370), (x1 - 30, 1360)], RED, 8)
    note(x1 + 100, 1700, "rich + single\n= trouble", f=hand_s, angle=5)
    note(x1 + 90, 2470, "poor guy,\nno say in it", f=hand_s, fill=RED, angle=-4)
    note(x1 + 90, boxes2[0][2], "Mrs. Bennet\nenergy", f=hand_s, angle=3)
    note(x0, y_end + 170, "reread #4", f=hand_s, angle=-1.5)
    hx, hy = x0 + 560, y_end + 250                     # a small drawn heart
    heart = [(hx + 46 * math.sin(t) ** 3, hy - (37 * math.cos(t) - 15 * math.cos(2 * t) - 6 * math.cos(3 * t) - 2 * math.cos(4 * t)))
             for t in [k * 0.1 for k in range(64)]]
    wobbly(md, heart, RED, 9)
    note(x0 + 680, y_end + 170, "still the best opening in English", f=hand_s, angle=-1.5)
    note(x0 + 1500, y_end + 380, "\u2014 J. A., 1813", f=hand, fill=INK)

    img.alpha_composite(paper); img.alpha_composite(marks); img.alpha_composite(text)
    img.save(out)
    return img


if __name__ == "__main__":
    import sys
    if "--garment" in sys.argv:
        # for print on fabric: no paper, opaque highlighter (DTG prints soft transparency poorly)
        YELLOW, PINK = (255, 226, 120, 255), (255, 178, 206, 255)
        im = main("page-garment.png", with_paper=False)
        im.resize((W // 6, H // 6), Image.LANCZOS).save("page-garment-preview.png")
        print("page-garment.png", im.size); raise SystemExit
    im = main()
    im.resize((W // 6, H // 6), Image.LANCZOS).save("page-preview.png")
    print("page.png", im.size)
