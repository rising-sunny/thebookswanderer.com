"""Cover for The Jane Austen Puzzle Book: cream paper, double rule, Hugh Thomson's
frontispiece of 1894 as clean ink, quiet type and the round logo."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from book import round_logo

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"
DPI = 300
mm = lambda v: v / 25.4 * DPI
pt = lambda v: int(v / 72 * DPI)
F = lambda n, s: ImageFont.truetype(f"{FONTS}/{n}", pt(s))
PAPER = (246, 240, 225); INK = (38, 52, 44); ACC = (122, 52, 40)


def ink_drawing(path, box):
    g = np.asarray(Image.open(path).convert("L").crop(box)).astype(float)
    paper = np.percentile(g, 90)
    a = np.clip((paper * 0.93 - g) / (paper * 0.55), 0, 1) ** 0.8      # ink coverage 0..1
    out = np.empty(g.shape + (3,))
    for i in range(3):
        out[..., i] = PAPER[i] * (1 - a) + INK[i] * a
    return Image.fromarray(out.astype(np.uint8))


def front(W, H):
    im = Image.new("RGB", (W, H), PAPER); d = ImageDraw.Draw(im)
    o, i = mm(10), mm(12.5)
    d.rectangle((o, o, W - o, H - o), outline=INK, width=5)
    d.rectangle((i, i, W - i, H - i), outline=INK, width=2)
    for x in (o, W - o):
        for y in (o, H - o):
            s = mm(2.6); d.rectangle((x - s, y - s, x + s, y + s), fill=PAPER, outline=INK, width=3)
            d.rectangle((x - s * .4, y - s * .4, x + s * .4, y + s * .4), fill=ACC)
    cx = W / 2
    d.text((cx, mm(30)), "T H E", font=F("Karla-700.ttf", 11), fill=ACC, anchor="mm")
    d.text((cx, mm(47)), "Jane Austen", font=F("Playfair-500i.ttf", 54), fill=INK, anchor="mm")
    d.text((cx, mm(66)), "Puzzle Book", font=F("Playfair-600.ttf", 30), fill=INK, anchor="mm")
    d.line((cx - mm(26), mm(77), cx - mm(3), mm(77)), fill=ACC, width=3); d.line((cx + mm(3), mm(77), cx + mm(26), mm(77)), fill=ACC, width=3)
    d.rectangle((cx - mm(1), mm(77) - mm(1), cx + mm(1), mm(77) + mm(1)), fill=ACC)
    art = ink_drawing("ia/front.jpg", (250, 330, 1880, 2735))
    aw = int(mm(92)); art = art.resize((aw, int(aw * art.height / art.width)), Image.LANCZOS)
    ay = int(mm(86)); im.paste(art, (int(cx - aw / 2), ay))
    y = ay + art.height + mm(7)
    d.text((cx, y), "Word searches, cryptograms, crosswords", font=F("Playfair-500i.ttf", 14), fill=INK, anchor="mm")
    d.text((cx, y + mm(7)), "and quotations from her six novels", font=F("Playfair-500i.ttf", 14), fill=INK, anchor="mm")
    lg, m = round_logo(int(mm(15)))
    logo = Image.open("/home/user/thebookswanderer.com/assets/logo-hero.webp")  # colour version for the cover
    from PIL import ImageOps
    box = ImageOps.invert(logo.convert("L")).point(lambda v: 255 if v > 24 else 0).getbbox()
    logo = logo.convert("RGB").crop(box).resize(lg.size, Image.LANCZOS)
    im.paste(logo, (int(cx - lg.width / 2), int(H - mm(17.5) - lg.height)), m)
    return im


if __name__ == "__main__" and False:
    W, H = int(8.5 * DPI), int(11 * DPI)
    f = front(W, H); f.save("front.png"); f.resize((W // 4, H // 4)).save("front_prev.jpg")


def back(W, H):
    im = Image.new("RGB", (W, H), PAPER); d = ImageDraw.Draw(im)
    o, i = mm(10), mm(12.5)
    d.rectangle((o, o, W - o, H - o), outline=INK, width=5)
    d.rectangle((i, i, W - i, H - i), outline=INK, width=2)
    for x in (o, W - o):
        for y in (o, H - o):
            s = mm(2.6); d.rectangle((x - s, y - s, x + s, y + s), fill=PAPER, outline=INK, width=3)
            d.rectangle((x - s * .4, y - s * .4, x + s * .4, y + s * .4), fill=ACC)
    cx = W / 2
    d.text((cx, mm(36)), "The Jane Austen Puzzle Book", font=F("Playfair-500i.ttf", 26), fill=INK, anchor="mm")
    d.line((cx - mm(20), mm(46), cx + mm(20), mm(46)), fill=ACC, width=3)
    text = ("Six novels, fifty-four puzzles. Find the Bennet sisters in a word search, crack the first line of "
            "Pride and Prejudice in code, fill a crossword with the houses of Emma and Persuasion, and match "
            "famous lines to the characters who said them. Then come missing words, anagrams and a quiz for each book. Every quotation comes from Austen's own text.")
    f = F("Playfair-500i.ttf", 13); y = mm(56); line = ""
    for w in text.split():
        t = (line + " " + w).strip()
        if d.textlength(t, font=f) > mm(150): d.text((cx, y), line, font=f, fill=INK, anchor="ma"); y += mm(7.4); line = w
        else: line = t
    d.text((cx, y), line, font=f, fill=INK, anchor="ma")
    # two real pages from the book
    import subprocess
    for k, (page, x) in enumerate(((6, cx - mm(62)), (7, cx + mm(4)))):
        subprocess.run(["pdftoppm", "-r", "100", "-f", str(page), "-l", str(page), "-png", "-singlefile", "austen-interior.pdf", "bk"], check=True)
        pg = Image.open("bk.png").convert("RGB"); pw = int(mm(58)); pg = pg.resize((pw, int(pw * 11 / 8.5)), Image.LANCZOS)
        im.paste(pg, (int(x), int(mm(102)))); d.rectangle((x, mm(102), x + pw, mm(102) + pg.height), outline=INK, width=2)
    y = mm(102) + int(mm(58) * 11 / 8.5) + mm(12)
    for line in ("Pride and Prejudice · Emma · Sense and Sensibility", "Persuasion · Northanger Abbey · Mansfield Park"):
        d.text((cx, y), line, font=F("Karla-400.ttf", 10.5), fill=INK, anchor="mm"); y += mm(6.5)
    d.text((cx, y + mm(4)), "Solutions at the back · 8.5 × 11 in · 76 pages", font=F("Karla-400.ttf", 9.5), fill=(110, 105, 95), anchor="mm")
    lg, m = round_logo(int(mm(15)))
    logo = Image.open("/home/user/thebookswanderer.com/assets/logo-hero.webp")
    from PIL import ImageOps
    box = ImageOps.invert(logo.convert("L")).point(lambda v: 255 if v > 24 else 0).getbbox()
    logo = logo.convert("RGB").crop(box).resize(lg.size, Image.LANCZOS)
    lx, ly = int(i + mm(8)), int(H - i - mm(8) - lg.height)
    im.paste(logo, (lx, ly), m)
    d.text((lx + lg.width + mm(4), ly + lg.height / 2), "thebookswanderer.com", font=F("Karla-700.ttf", 9), fill=ACC, anchor="lm")
    return im


def print_cover(out="austen-cover.pdf"):
    """One piece for Lulu: 1259 x 810 pt for 76 pages, 9 pt bleed, 17 pt spine, no spine text."""
    s = DPI / 72
    W, H = int(1259 * s), int(810 * s); bleed = int(9 * s); trim_w = int(612 * s)
    full = Image.new("RGB", (W, H), PAPER)
    full.paste(back(trim_w, int(792 * s)), (bleed, bleed))
    full.paste(front(trim_w, int(792 * s)), (W - bleed - trim_w, bleed))
    full.save(out, resolution=DPI); full.resize((W // 4, H // 4)).save("cover_prev.jpg")
if __name__ == "__main__":
    print_cover()
