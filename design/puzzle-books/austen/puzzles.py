"""Literary puzzle pages: a word search and a cryptogram from a public domain novel."""
import random, string
from PIL import Image, ImageDraw, ImageFont

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"
DPI = 300
mm = lambda v: v / 25.4 * DPI
pt = lambda v: int(v / 72 * DPI)
PW, PH = int(mm(210)), int(mm(297))
INK, GREY, ACC = (30, 40, 35), (110, 110, 105), (120, 30, 45)
F = lambda n, s: ImageFont.truetype(f"{FONTS}/{n}", pt(s))
DIRS = [(0, 1), (1, 0), (1, 1), (-1, 1), (0, -1), (-1, 0), (-1, -1), (1, -1)]


def page_head(d, kicker, title, sub):
    d.text((PW / 2, mm(22)), kicker, font=F("Karla-700.ttf", 9), fill=ACC, anchor="mm")
    d.text((PW / 2, mm(33)), title, font=F("Playfair-500i.ttf", 26), fill=INK, anchor="mm")
    d.text((PW / 2, mm(43)), sub, font=F("Playfair-500i.ttf", 11), fill=GREY, anchor="mm")
    d.line((PW / 2 - mm(25), mm(50), PW / 2 - mm(2), mm(50)), fill=ACC, width=2)
    d.line((PW / 2 + mm(2), mm(50), PW / 2 + mm(25), mm(50)), fill=ACC, width=2)
    d.rectangle((PW / 2 - mm(0.8), mm(50) - mm(0.8), PW / 2 + mm(0.8), mm(50) + mm(0.8)), fill=ACC)


def word_search(words, n=15, seed=7):
    rnd = random.Random(seed)
    for _ in range(500):
        g = [[""] * n for _ in range(n)]; placed = {}
        ok = True
        for w in sorted(words, key=len, reverse=True):
            for _ in range(400):
                dy, dx = rnd.choice(DIRS); y, x = rnd.randrange(n), rnd.randrange(n)
                cells = [(y + dy * i, x + dx * i) for i in range(len(w))]
                if all(0 <= a < n and 0 <= b < n and g[a][b] in ("", w[i]) for i, (a, b) in enumerate(cells)):
                    for i, (a, b) in enumerate(cells): g[a][b] = w[i]
                    placed[w] = cells; break
            else:
                ok = False; break
        if ok: break
    for row in g:
        for i, c in enumerate(row):
            if not c: row[i] = rnd.choice(string.ascii_uppercase)
    return g, placed


def ws_page(words, title, sub, out, solution=False):
    page = Image.new("RGB", (PW, PH), "white"); d = ImageDraw.Draw(page)
    page_head(d, "WORD SEARCH", title, sub)
    g, placed = word_search([w.replace(" ", "") for w in words])
    n = len(g); cell = mm(10.5); x0 = (PW - n * cell) / 2; y0 = mm(62)
    if solution:
        for cells in placed.values():
            (a0, b0), (a1, b1) = cells[0], cells[-1]
            d.line((x0 + (b0 + .5) * cell, y0 + (a0 + .5) * cell, x0 + (b1 + .5) * cell, y0 + (a1 + .5) * cell),
                   fill=(235, 205, 205), width=int(cell * 0.7))
    d.rounded_rectangle((x0 - mm(4), y0 - mm(4), x0 + n * cell + mm(4), y0 + n * cell + mm(4)), radius=mm(3), outline=(190, 185, 175), width=3)
    for y in range(n):
        for x in range(n):
            d.text((x0 + (x + .5) * cell, y0 + (y + .5) * cell), g[y][x], font=F("Karla-700.ttf", 15), fill=INK, anchor="mm")
    # word list in three columns
    ly = y0 + n * cell + mm(14); colw = mm(58); lx0 = PW / 2 - 1.5 * colw
    for i, w in enumerate(words):
        cx = lx0 + (i % 3) * colw; cy = ly + (i // 3) * mm(8)
        d.rectangle((cx, cy - mm(1.5), cx + mm(3), cy + mm(1.5)), outline=GREY, width=2)
        d.text((cx + mm(5.5), cy), w.title(), font=F("Playfair-600.ttf", 12), fill=INK, anchor="lm")
    page.save(out); return page


def cryptogram(quote, seed=3):
    rnd = random.Random(seed); A = list(string.ascii_uppercase)
    while True:
        B = A[:]; rnd.shuffle(B)
        if all(a != b for a, b in zip(A, B)): break
    return dict(zip(A, B))


def crypto_page(quote, author, out, hints=("E", "T")):
    page = Image.new("RGB", (PW, PH), "white"); d = ImageDraw.Draw(page)
    page_head(d, "CRYPTOGRAM", "A famous first line", "Each letter stands for another. Crack the code to read the quote.")
    key = cryptogram(quote); q = quote.upper()
    bw, gap = mm(7.4), mm(0.9); x0 = mm(22); xmax = PW - mm(22); y = mm(64)
    words = q.split(" "); x = x0
    def width(w): return len(w) * (bw + gap)
    for w in words:
        if x + width(w) > xmax:
            x = x0; y += mm(20)
        for ch in w:
            if ch.isalpha():
                given = key[ch] in [key[h] for h in hints]
                d.line((x, y + mm(8), x + bw, y + mm(8)), fill=(150, 150, 150), width=3)
                if given:
                    d.text((x + bw / 2, y + mm(4.5)), ch, font=F("Playfair-600.ttf", 15), fill=ACC, anchor="mm")
                d.text((x + bw / 2, y + mm(13)), key[ch], font=F("Karla-700.ttf", 12), fill=GREY, anchor="mm")
            else:
                d.text((x + bw / 2, y + mm(6)), ch, font=F("Playfair-600.ttf", 15), fill=INK, anchor="mm")
            x += bw + gap
        x += bw * 0.8
    y += mm(26)
    d.text((PW - mm(22), y), author, font=F("Playfair-500i.ttf", 12), fill=GREY, anchor="rm")
    hint = "Two letters are given: " + " and ".join(f"{key[h]} = {h}" for h in hints) + "."
    d.text((PW / 2, y + mm(50)), hint, font=F("Playfair-500i.ttf", 11), fill=GREY, anchor="mm")
    # a key table to keep track
    ty = y + mm(16); cw = (PW - mm(44)) / 26
    for i, ch in enumerate(string.ascii_uppercase):
        cx = mm(22) + i * cw
        d.rectangle((cx, ty, cx + cw, ty + mm(14)), outline=(190, 185, 175), width=2)
        d.line((cx, ty + mm(7), cx + cw, ty + mm(7)), fill=(190, 185, 175), width=2)
        d.text((cx + cw / 2, ty + mm(3.5)), ch, font=F("Karla-700.ttf", 9), fill=GREY, anchor="mm")
    d.text((mm(22), ty - mm(4)), "Code letter", font=F("Karla-400.ttf", 8), fill=GREY, anchor="lm")
    d.text((mm(22), ty + mm(18)), "Real letter goes in the box below each one", font=F("Karla-400.ttf", 8), fill=GREY, anchor="lm")
    page.save(out); return page


if __name__ == "__main__":
    words = ["ELIZABETH", "DARCY", "JANE", "BINGLEY", "LYDIA", "WICKHAM", "COLLINS", "CHARLOTTE",
             "PEMBERLEY", "LONGBOURN", "NETHERFIELD", "MERYTON", "ROSINGS", "KITTY", "GEORGIANA"]
    a = ws_page(words, "Pride and Prejudice", "Jane Austen, 1813 · fifteen names and places", "ws.png")
    b = ws_page(words, "Pride and Prejudice", "Solution", "ws-sol.png", solution=True)
    c = crypto_page("It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.",
                    "Jane Austen, Pride and Prejudice", "crypto.png")
    s = Image.new("RGB", (1250, 877), "gray")
    s.paste(a.resize((620, 877)), (0, 0)); s.paste(c.resize((620, 877)), (630, 0)); s.save("prev.jpg")
