"""'Annotated' artwork, second title: the opening of A Christmas Carol (Dickens, 1843, public domain)
as a page someone has read with a highlighter and a pen. Reuses the helpers of annotated_page.py.

  python annotated_carol.py [fonts_dir] [out_dir]
  # writes carol-poster-2x3.png, -3x4, -4x5 and carol-page-preview.jpg
Fonts: EB Garamond and Caveat (SIL OFL 1.1), variable TTFs in fonts_dir.
"""
import math
import random
import sys
from pathlib import Path
from PIL import Image, ImageDraw
import annotated_page as ap
from annotated_page import font, layout, span, wobbly

if len(sys.argv) > 1:
    ap.F = sys.argv[1].rstrip("/") + "/"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
W, H = ap.W, 4800                      # taller than the P&P page: this text runs longer
ap.H = H
PAPER, INK, PEN, RED = ap.PAPER, ap.INK, ap.PEN, ap.RED
YELLOW, PINK = ap.YELLOW, ap.PINK
GREEN = (38, 92, 62, 235)

TEXT = ("Marley was dead: to begin with. There is no doubt whatever about that. The register of his "
        "burial was signed by the clergyman, the clerk, the undertaker, and the chief mourner. "
        "Scrooge signed it: and Scrooge’s name was good upon ’Change, for anything he chose "
        "to put his hand to. Old Marley was as dead as a door-nail.")
TEXT2 = ("Mind! I don’t mean to say that I know, of my own knowledge, what there is particularly "
         "dead about a door-nail. I might have been inclined, myself, to regard a coffin-nail as the "
         "deadest piece of ironmongery in the trade.")


def idx(words, start):
    return next(i for i, w in enumerate(words) if w.startswith(start))


def page(with_paper=False, seed=5):
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

    x0, x1 = 470, W - 980
    for t, y in (("STAVE ONE.", 400), ("MARLEY’S GHOST.", 560)):
        td.text(((x0 + x1) / 2 - td.textlength(t, font=caps) / 2, y), t, font=caps, fill=INK)
    words = TEXT.split(" ")
    boxes, y_end = ap.layout(td, words, x0, x1, 900, body, 214)
    words2 = TEXT2.split(" ")
    boxes2, y_end = ap.layout(td, words2, x0 + 120, x1, y_end + 110, body, 214)
    for w, bx, by, _ in boxes + boxes2:
        td.text((bx, by), w, font=body, fill=INK)

    # highlighter: "Marley was dead: to begin with." (yellow), "Scrooge signed it:" (pink)
    for (a, y, b) in span(boxes, 0, 6, body):
        md.rounded_rectangle([a - 14, y + 22, b + 18, y + 170], radius=24, fill=YELLOW)
    s = idx(words, "Scrooge")
    for (a, y, b) in span(boxes, s, 3, body):
        md.rounded_rectangle([a - 14, y + 22, b + 18, y + 170], radius=24, fill=PINK)
    # pen: wavy underline under "as dead as a door-nail."
    d0 = len(words) - 5
    for (a, y, b) in span(boxes, d0, 5, body):
        pts = [(x, y + 182 + 9 * math.sin(x / 38)) for x in range(int(a), int(b), 12)]
        wobbly(md, pts, PEN, 9)
    # pen: circle round "clergyman,"
    i = idx(words, "clergyman")
    _, bx, by, bx1 = boxes[i]
    cx, cy, rx, ry = (bx + bx1) / 2, by + 95, (bx1 - bx) / 2 + 46, 105
    pts = [(cx + rx * math.cos(a) + random.uniform(-4, 4), cy + ry * math.sin(a) + random.uniform(-4, 4))
           for a in [k * 0.12 - 0.4 for k in range(60)]]
    wobbly(md, pts, RED, 10)
    # pen: bracket beside the "Mind!" paragraph
    yb0, yb1 = boxes2[0][2] + 30, boxes2[-1][2] + 180
    wobbly(md, [(x0 + 70, yb0), (x0 + 40, yb0 + 20), (x0 + 40, yb1 - 20), (x0 + 70, yb1)], PEN, 9)

    def note(x, y, s, f=hand, fill=PEN, angle=0):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        ld.text((x, y), s, font=f, fill=fill)
        if angle:
            layer = layer.rotate(angle, center=(x, y), resample=Image.BICUBIC)
        marks.alpha_composite(layer)
    note(x1 + 90, boxes[0][2] - 40, "starts with\na funeral.\nin December.", angle=4)
    note(x1 + 90, boxes[idx(words, "clergyman")][2] - 90, "so we\nbelieve him", f=hand_s, angle=4)
    note(x1 + 90, boxes[idx(words, "Scrooge")][2] + 20, "Scrooge signed\nit!!", f=hand_s, fill=RED, angle=-5)
    note(x1 + 90, boxes[-1][2] - 20, "why a door-nail?!", f=hand_s, fill=RED, angle=-3)
    note(x1 + 90, boxes2[0][2], "the narrator\ncan’t resist", f=hand_s, angle=3)
    note(x0, y_end + 170, "reread every December", f=hand_s, angle=-1.5)
    hx, hy = x0 + 1180, y_end + 250
    heart = [(hx + 46 * math.sin(t) ** 3, hy - (37 * math.cos(t) - 15 * math.cos(2 * t) - 6 * math.cos(3 * t) - 2 * math.cos(4 * t)))
             for t in [k * 0.1 for k in range(64)]]
    wobbly(md, heart, RED, 9)
    note(x0, y_end + 350, "best ghost story opener", f=hand_s, angle=-1.5)
    note(x0 + 1450, y_end + 520, "— C. D., 1843", f=hand, fill=INK)

    img.alpha_composite(paper); img.alpha_composite(marks); img.alpha_composite(text)
    return img


def poster(width, out, height=6000):
    art = page()
    art = art.crop(art.getchannel("A").getbbox())
    margin = int(width * 0.11)
    scale = (width - 2 * margin) / art.width
    if art.height * scale > height * 0.78:
        scale = height * 0.78 / art.height
    art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
    img = Image.new("RGBA", (width, height), PAPER)
    top = int((height - art.height) * 0.42)
    img.alpha_composite(art, ((width - art.width) // 2, top))
    d = ImageDraw.Draw(img)
    cap = font("EBGaramond.ttf", int(width * 0.026), 450)
    t = "A CHRISTMAS CAROL  ·  CHARLES DICKENS  ·  1843"
    d.text(((width - d.textlength(t, font=cap)) / 2, height - int(height * 0.075)), t, font=cap, fill=(90, 80, 68, 255))
    img.convert("RGB").save(out, optimize=True)
    img.convert("RGB").resize((width // 8, height // 8), Image.LANCZOS).save(str(out).replace(".png", "-preview.jpg"), quality=88)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    poster(4000, OUT / "carol-poster-2x3.png")
    poster(4500, OUT / "carol-poster-3x4.png")
    poster(4800, OUT / "carol-poster-4x5.png")
    print("done")
