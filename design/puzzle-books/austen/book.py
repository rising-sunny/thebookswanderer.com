"""The Jane Austen Puzzle Book: interior pages, US Letter, black and white."""
import random, string, re
from PIL import Image, ImageDraw, ImageFont
from content import NOVELS
from crossword import build as crossword
from puzzles import word_search, cryptogram

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"
DPI = 300
mm = lambda v: v / 25.4 * DPI
pt = lambda v: int(v / 72 * DPI)
PW, PH = int(8.5 * DPI), int(11 * DPI)
INK, GREY, LIGHT = (25, 25, 25), (100, 100, 100), (175, 175, 175)
F = lambda n, s: ImageFont.truetype(f"{FONTS}/{n}", pt(s))
SERIF, ITAL, SANS, SANSB = "Playfair-600.ttf", "Playfair-500i.ttf", "Karla-400.ttf", "Karla-700.ttf"
ORD = ["One", "Two", "Three", "Four", "Five", "Six"]


class Page:
    def __init__(self, no):
        self.no = no
        self.im = Image.new("RGB", (PW, PH), "white"); self.d = ImageDraw.Draw(self.im)
        self.cx = PW / 2 + (mm(3) if no % 2 else -mm(3))     # away from the spine
    def folio(self):
        self.d.text((self.cx, PH - mm(12)), str(self.no), font=F(SANS, 9), fill=GREY, anchor="mm")
    def head(self, kicker, title, sub=None, y=mm(24)):
        d, cx = self.d, self.cx
        d.text((cx, y), kicker.upper(), font=F(SANSB, 9), fill=GREY, anchor="mm")
        d.text((cx, y + mm(11)), title, font=F(ITAL, 24), fill=INK, anchor="mm")
        if sub: d.text((cx, y + mm(20)), sub, font=F(ITAL, 11), fill=GREY, anchor="mm")
        yy = y + (mm(27) if sub else mm(20))
        d.line((cx - mm(22), yy, cx - mm(2.5), yy), fill=INK, width=2); d.line((cx + mm(2.5), yy, cx + mm(22), yy), fill=INK, width=2)
        d.rectangle((cx - mm(0.8), yy - mm(0.8), cx + mm(0.8), yy + mm(0.8)), fill=INK)
        return yy + mm(10)
    def para(self, text, y, width=mm(140), font=(SERIF, 11.5), lead=mm(6.6), align="left", fill=INK):
        f = F(*font); x0 = self.cx - width / 2
        for block in text.split("\n"):
            line = ""
            for w in block.split():
                t = (line + " " + w).strip()
                if self.d.textlength(t, font=f) > width:
                    self._line(line, x0, y, width, f, align, fill); y += lead; line = w
                else: line = t
            if line: self._line(line, x0, y, width, f, align, fill); y += lead
            y += lead * 0.5
        return y
    def _line(self, s, x0, y, width, f, align, fill):
        if align == "center": self.d.text((x0 + width / 2, y), s, font=f, fill=fill, anchor="ma")
        else: self.d.text((x0, y), s, font=f, fill=fill)


def sub(d, cx):
    """A Page view on an existing drawing, for text blocks placed by hand."""
    v = Page.__new__(Page); v.d = d; v.cx = cx; return v


def end_punct(q):
    return q if q[-1] in ".!?" else q.rstrip(",;:") + "…"


# ---------- puzzle pages ----------
def ws_page(p, n, sol=None, scale=1.0, top=None, which="words"):
    d = p.d; words = n[which]
    g, placed = sol or word_search(words, seed=sum(map(ord, n["key"] + which)))
    size = len(g); cell = mm(10.4) * scale
    x0 = p.cx - size * cell / 2; y0 = top if top is not None else p.head("Word search", n["title"],
        "Fifteen names and places from the novel" if which == "words" else "Fifteen words from the world of the novel")
    if sol:
        for cells in placed.values():
            (a0, b0), (a1, b1) = cells[0], cells[-1]
            d.line((x0 + (b0 + .5) * cell, y0 + (a0 + .5) * cell, x0 + (b1 + .5) * cell, y0 + (a1 + .5) * cell), fill=(200, 200, 200), width=int(cell * 0.62))
    d.rounded_rectangle((x0 - mm(3), y0 - mm(3), x0 + size * cell + mm(3), y0 + size * cell + mm(3)), radius=mm(3), outline=LIGHT, width=3)
    for y in range(size):
        for x in range(size):
            d.text((x0 + (x + .5) * cell, y0 + (y + .5) * cell), g[y][x], font=F(SANSB, 14.5 * scale), fill=INK, anchor="mm")
    if sol: return y0 + size * cell
    ly = y0 + size * cell + mm(13); colw = mm(55); lx0 = p.cx - 1.5 * colw
    for i, w in enumerate(words):
        cx = lx0 + (i % 3) * colw; cy = ly + (i // 3) * mm(8)
        d.rectangle((cx, cy - mm(1.5), cx + mm(3), cy + mm(1.5)), outline=GREY, width=2)
        d.text((cx + mm(5.5), cy), w.title(), font=F(SERIF, 12), fill=INK, anchor="lm")
    return (g, placed)


def crypto_page(p, n, hints=("E", "T"), which="crypto"):
    d = p.d; quote, src = n[which]
    y = p.head("Cryptogram", n["title"], "Each letter stands for another. Crack the code to read the line.")
    key = cryptogram(quote, seed=sum(map(ord, n["key"] + which))); q = quote.upper()
    k = 1.0 if len(q) <= 120 else 0.84 if len(q) <= 160 else 0.74     # long lines get smaller letters
    bw, gap = mm(7.6) * k, mm(0.9) * k; xl = p.cx - mm(84); xr = p.cx + mm(84); x = xl; y += mm(6)
    for w in q.split(" "):
        if x + len(w) * (bw + gap) > xr: x = xl; y += mm(21) * (0.5 + 0.5 * k)
        for ch in w:
            if ch.isalpha():
                d.line((x, y + mm(8), x + bw, y + mm(8)), fill=GREY, width=3)
                if ch in hints: d.text((x + bw / 2, y + mm(4.5)), ch, font=F(SERIF, 15 * k), fill=INK, anchor="mm")
                d.text((x + bw / 2, y + mm(13)), key[ch], font=F(SANSB, 12 * k), fill=GREY, anchor="mm")
            else:
                d.text((x + bw / 2, y + mm(6)), ch, font=F(SERIF, 15 * k), fill=INK, anchor="mm")
            x += bw + gap
        x += bw * 0.8
    y += mm(28)
    d.text((xr, y), f"{n['title']}, {src}" if src.startswith("Chapter") else f"{src}, {n['title']}", font=F(ITAL, 11.5), fill=GREY, anchor="rm")
    ty = y + mm(16); cw = mm(168) / 26
    d.text((xl, ty - mm(4)), "Keep track of the code here: write the real letter under each code letter.", font=F(SANS, 8.5), fill=GREY, anchor="lm")
    for i, ch in enumerate(string.ascii_uppercase):
        c = xl + i * cw
        d.rectangle((c, ty, c + cw, ty + mm(14)), outline=LIGHT, width=2)
        d.line((c, ty + mm(7), c + cw, ty + mm(7)), fill=LIGHT, width=2)
        d.text((c + cw / 2, ty + mm(3.5)), ch, font=F(SANSB, 9), fill=GREY, anchor="mm")
    hint = "Two letters are filled in to start you off: " + " and ".join(f"{key[h]} is {h}" for h in hints) + "."
    d.text((p.cx, ty + mm(24)), hint, font=F(ITAL, 11), fill=GREY, anchor="mm")
    return key


def cross_grid(p, entries, h, w, y0, cell, solved=False):
    d = p.d; x0 = p.cx - w * cell / 2
    cells = {}
    for num, word, r, c, dirn in entries:
        for i, ch in enumerate(word):
            cells[(r + (i if dirn == "down" else 0), c + (i if dirn == "across" else 0))] = ch
    starts = {(r, c): num for num, _, r, c, _ in entries}
    for (r, c), ch in cells.items():
        bx = (x0 + c * cell, y0 + r * cell, x0 + (c + 1) * cell, y0 + (r + 1) * cell)
        d.rectangle(bx, outline=INK, width=3)
        if (r, c) in starts:
            d.text((bx[0] + mm(0.7), bx[1] + mm(0.4)), str(starts[(r, c)]), font=F(SANS, 6.5 if cell > mm(7) else 5), fill=INK)
        if solved:
            d.text(((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2 + mm(0.6)), ch, font=F(SANSB, 12 if cell > mm(7) else 8), fill=INK, anchor="mm")
    return y0 + h * cell


def cross_page(p, n):
    entries, h, w = crossword([a for a, _ in n["cross"]], seed=sum(map(ord, n["key"])))
    clue = dict(n["cross"])
    y = p.head("Crossword", n["title"], "Every answer is a name, a place or a thing from the novel")
    cell = min(mm(9.5), mm(168) / w, mm(118) / h)
    y = cross_grid(p, entries, h, w, y, cell) + mm(9)
    d = p.d; colx = (p.cx - mm(86), p.cx + mm(4)); f = F(SERIF, 10.5)
    for k, dirn in enumerate(("across", "down")):
        yy = y; x = colx[k]
        d.text((x, yy), dirn.upper(), font=F(SANSB, 9.5), fill=INK); yy += mm(6.5)
        for num, word, *_rest in sorted(e for e in entries if e[4] == dirn):
            txt = f"{clue[word]} ({len(word)})"
            sub_ = sub(d, x + mm(43.5))
            d.text((x, yy), str(num), font=F(SANSB, 10), fill=INK)
            yy = sub_.para(txt, yy, width=mm(72), font=(SERIF, 10.5), lead=mm(5.2), fill=INK) - mm(1.3)
    return entries, h, w


def who_page(p, n):
    d = p.d
    y = p.head("Who said it?", n["title"], "Match each line to the character who said or wrote it")
    names = sorted({s for _, s in n["who"]} | set(n["extra"]))
    rnd = random.Random(n["key"]); quotes = n["who"][:]; rnd.shuffle(quotes)
    for i, (q, s) in enumerate(quotes):
        d.text((p.cx - mm(80), y), f"{i + 1}.", font=F(SANSB, 11), fill=INK)
        sub_ = sub(d, p.cx + mm(4))
        y = sub_.para(f"“{end_punct(q)}”", y, width=mm(152), font=(ITAL, 12.5), lead=mm(7)) - mm(1)
        d.line((p.cx + mm(20), y + mm(4), p.cx + mm(80), y + mm(4)), fill=LIGHT, width=2)
        y += mm(12)
    y += mm(4)
    d.text((p.cx, y), "THE SPEAKERS", font=F(SANSB, 9), fill=GREY, anchor="mm")
    y += mm(8)
    line = "   ·   ".join(names)
    sub_ = sub(d, p.cx)
    sub_.para(line, y, width=mm(160), font=(SERIF, 11.5), lead=mm(7), align="center")
    return quotes


def missing_page(p, n):
    d = p.d
    y = p.head("Missing words", n["title"], "Each line has lost a word. Find it in the list below.")
    bank = []
    for i, (q, w) in enumerate(n["missing"]):
        q = q[0].upper() + q[1:]
        k = q.lower().index(w.lower()); gap = "_" * max(8, len(w) + 3)
        line = f"“{end_punct(q[:k] + gap + q[k + len(w):])}”"
        d.text((p.cx - mm(80), y), f"{i + 1}.", font=F(SANSB, 11), fill=INK)
        y = sub(d, p.cx + mm(4)).para(line, y, width=mm(152), font=(ITAL, 12.5), lead=mm(7.2)) + mm(5)
        bank.append(q[k:k + len(w)].lower())
    random.Random(n["key"]).shuffle(bank)
    y += mm(6)
    d.text((p.cx, y), "THE MISSING WORDS", font=F(SANSB, 9), fill=GREY, anchor="mm")
    sub(d, p.cx).para("   ·   ".join(bank), y + mm(7), width=mm(160), font=(SERIF, 12), lead=mm(7), align="center")


def scramble(w, rnd):
    w = w.upper()
    for _ in range(50):
        s = "".join(rnd.sample(w, len(w)))
        if s != w and all(s[i:i + 3] != w[i:i + 3] for i in range(len(w) - 2)): return s
    return w[::-1]


def anagram_page(p, n):
    d = p.d
    y = p.head("Anagrams", n["title"], "Unscramble the names of ten characters and places")
    rnd = random.Random(n["key"] + "ana")
    names = [w for w in n["words"] if len(w) >= 5][:10]
    out = []
    for i, w in enumerate(names):
        s_ = scramble(w, rnd); out.append((s_, w))
        yy = y + i * mm(19)
        d.text((p.cx - mm(78), yy), f"{i + 1}.", font=F(SANSB, 11), fill=INK)
        d.text((p.cx - mm(66), yy), "  ".join(s_), font=F(SANSB, 14), fill=INK)
        d.line((p.cx + mm(18), yy + mm(6), p.cx + mm(80), yy + mm(6)), fill=LIGHT, width=2)
    return out


def quiz_page(p, n):
    d = p.d
    y = p.head("Quiz", n["title"], "How well do you know the story? Circle one answer for each question.")
    rnd = random.Random(n["key"] + "quiz"); answers = []
    for i, (q, right, *wrong) in enumerate(n["quiz"]):
        opts = [right] + wrong; rnd.shuffle(opts); answers.append("ABC"[opts.index(right)])
        d.text((p.cx - mm(80), y), f"{i + 1}.", font=F(SANSB, 11), fill=INK)
        y = sub(d, p.cx + mm(4)).para(q, y, width=mm(152), font=(SERIF, 12.5), lead=mm(7)) - mm(1)
        for k, o in enumerate(opts):
            d.text((p.cx - mm(68) + k * mm(53), y), f"{'ABC'[k]}  {o}", font=F(ITAL, 11), fill=INK)
        y += mm(14)
    return answers


def opener(p, n, i, blurb):
    d = p.d
    d.text((p.cx, mm(88)), f"CHAPTER {ORD[i].upper()}", font=F(SANSB, 10), fill=GREY, anchor="mm")
    d.text((p.cx, mm(108)), n["title"], font=F(ITAL, 34), fill=INK, anchor="mm")
    d.text((p.cx, mm(122)), str(n["year"]), font=F(SERIF, 13), fill=GREY, anchor="mm")
    d.line((p.cx - mm(22), mm(132), p.cx + mm(22), mm(132)), fill=INK, width=2)
    p.para(blurb, mm(146), width=mm(118), font=(ITAL, 13), lead=mm(7.6), align="center")
    p.para("Word searches  ·  Cryptograms  ·  Crossword  ·  Who said it?  ·  Missing words  ·  Anagrams  ·  Quiz", mm(205), width=mm(140), font=(SANS, 10), lead=mm(6), align="center", fill=GREY)


BLURBS = {
 "pp": "Five sisters, a mother set on seeing them married, and a proud gentleman from Derbyshire. Austen's working title was First Impressions, and they turn out to be wrong on both sides.",
 "emma": "Emma Woodhouse has lived nearly twenty-one years in the world with very little to distress or vex her. Then she takes up matchmaking.",
 "ss": "Two sisters, one led by her head and one by her heart, leave their home in Sussex for a cottage in Devonshire. This was Austen's first published novel.",
 "persuasion": "Eight years after she was persuaded to refuse him, Anne Elliot meets Captain Wentworth again. Austen's last finished novel, published after her death.",
 "na": "Catherine Morland has read a great many Gothic novels. A season in Bath and a visit to an old abbey teach her where stories end and life begins.",
 "mp": "Fanny Price is ten when she is sent to live with her rich cousins at Mansfield Park. Quiet and overlooked, she sees more than anyone thinks.",
}


# ---------- front matter, solutions, assembly ----------
LOGO = "/home/user/thebookswanderer.com/assets/logo-hero.webp"


def round_logo(px):
    from PIL import ImageOps
    im = Image.open(LOGO).convert("RGB")
    box = ImageOps.invert(im.convert("L")).point(lambda v: 255 if v > 24 else 0).getbbox()
    im = im.crop(box).resize((px, px), Image.LANCZOS).convert("L").convert("RGB")
    mask = Image.new("L", (px * 4, px * 4), 0); ImageDraw.Draw(mask).ellipse((0, 0, px * 4 - 1, px * 4 - 1), fill=255)
    return im, mask.resize((px, px), Image.LANCZOS)


def title_page(p):
    d = p.d
    d.text((p.cx, mm(70)), "THE", font=F(SANSB, 11), fill=GREY, anchor="mm")
    d.text((p.cx, mm(88)), "Jane Austen", font=F(ITAL, 46), fill=INK, anchor="mm")
    d.text((p.cx, mm(108)), "Puzzle Book", font=F(SERIF, 30), fill=INK, anchor="mm")
    d.line((p.cx - mm(22), mm(122), p.cx + mm(22), mm(122)), fill=INK, width=2)
    p.para("Word searches, cryptograms, crosswords and quotations from her six novels", mm(132), width=mm(110), font=(ITAL, 13), lead=mm(7.5), align="center", fill=GREY)
    im, m = round_logo(int(mm(26))); p.im.paste(im, (int(p.cx - mm(13)), int(mm(222))), m)
    d.text((p.cx, mm(254)), "The Books Wanderer", font=F(SERIF, 11), fill=GREY, anchor="mm")


def about_page(p):
    y = p.head("Before you begin", "How to play")
    p.para(
        "There is a chapter for each of Jane Austen's six novels, with nine puzzles in each.\n"
        "Word search. Fifteen names and places are hidden in the grid. They can run across, down or diagonally, forwards or backwards.\n"
        "Cryptogram. A line from the novel is written in code: every letter has been swapped for another. Two letters are given. Work out the rest from short words, repeated letters and the shape of the sentence.\n"
        "Crossword. Every answer is a name, a place or a thing from the book. The number in brackets is the length of the answer.\n"
        "Who said it? Six lines from the novel, and a list of speakers to choose from. A few names on the list said none of them.\n"
        "Missing words, anagrams and a short quiz close each chapter.\n"
        "The solutions are at the back of the book.", y, width=mm(150), font=(SERIF, 11.5), lead=mm(6.8))
    p.para("Every quotation is taken from the original text of the novels, which are in the public domain. "
           "Puzzles, clues and layout © 2026 The Books Wanderer. thebookswanderer.com", mm(236), width=mm(150), font=(ITAL, 9.5), lead=mm(5.5), fill=GREY)


def contents_page(p, starts, sol_start):
    y = p.head("Contents", "Contents")
    for i, n in enumerate(NOVELS):
        p.d.text((p.cx - mm(70), y), f"{ORD[i]}", font=F(SANS, 10), fill=GREY)
        p.d.text((p.cx - mm(45), y), n["title"], font=F(SERIF, 14), fill=INK)
        p.d.text((p.cx + mm(70), y), str(starts[i]), font=F(SERIF, 13), fill=INK, anchor="ra")
        y += mm(14)
    y += mm(6)
    p.d.text((p.cx - mm(45), y), "Solutions", font=F(SERIF, 14), fill=INK)
    p.d.text((p.cx + mm(70), y), str(sol_start), font=F(SERIF, 13), fill=INK, anchor="ra")


def notes_page(p, title="Notes"):
    d = p.d
    d.text((p.cx, mm(24)), title.upper(), font=F(SANSB, 9), fill=GREY, anchor="mm")
    for k in range(26):
        y = mm(40) + k * mm(8.5)
        d.line((p.cx - mm(80), y, p.cx + mm(80), y), fill=(215, 215, 215), width=2)


def build():
    pages = []
    def new():
        pg = Page(len(pages) + 1); pages.append(pg); return pg
    title_page(new()); about_page(new()); contents = new(); author = new()
    author.head("The author", "Jane Austen, 1775–1817")
    author.para("Jane Austen was born in the rectory at Steventon, in Hampshire, the seventh of eight children. "
                "She wrote from girlhood, first to amuse her family. Four of her novels came out in her lifetime, without her name on them; "
                "the title pages said only that they were by a lady. Persuasion and Northanger Abbey were published together a few months after her death in 1817.\n"
                "Two hundred years on, her characters are still quoted, argued over and loved. This book is a way to spend a little more time with them.",
                mm(70), width=mm(140), font=(SERIF, 12), lead=mm(7.4))
    starts, results, extra = [], [], []
    for i, n in enumerate(NOVELS):
        op = new(); starts.append(op.no); opener(op, n, i, BLURBS[n["key"]])
        ws = ws_page(new(), n); key = crypto_page(new(), n); cw = cross_page(new(), n); who = who_page(new(), n)
        ws2 = ws_page(new(), n, which="words2"); crypto_page(new(), n, which="crypto2")
        missing_page(new(), n); ana = anagram_page(new(), n); quiz = quiz_page(new(), n)
        results.append((n, ws, key, cw, who))
        extra.append((n, ws2, ana, quiz))
    sol_start = len(pages) + 1
    # word search solutions, four to a page
    grids = []
    for (n, ws, *_r), (_n, ws2, *_e) in zip(results, extra):
        grids += [(n, ws, "words", "names and places"), (n, ws2, "words2", "words")]
    for k in range(0, len(grids), 4):
        pg = new(); y = pg.head("Solutions", "Word searches")
        for j, (n, sol, which, label) in enumerate(grids[k:k + 4]):
            cx0 = pg.cx; pg.cx = cx0 + (-mm(44) if j % 2 == 0 else mm(44))
            top = y + (j // 2) * mm(102) + mm(9)
            pg.d.text((pg.cx, top - mm(7)), f"{n['title']}, {label}", font=F(ITAL, 11), fill=INK, anchor="mm")
            ws_page(pg, n, sol=sol, scale=0.5, top=top, which=which); pg.cx = cx0
    # crosswords, two to a page
    for k in range(0, 6, 2):
        pg = new(); y = pg.head("Solutions", "Crosswords")
        for j, (n, ws, key, (entries, h, w), who) in enumerate(results[k:k + 2]):
            pg.d.text((pg.cx, y), n["title"], font=F(ITAL, 12), fill=INK, anchor="mm")
            cell = min(mm(6.8), mm(150) / w, mm(90) / h)
            cross_grid(pg, entries, h, w, y + mm(6), cell, solved=True)
            y += mm(106)
    # cryptograms and who said it
    for half in (results[:3], results[3:]):
        pg = new(); y = pg.head("Solutions", "Cryptograms")
        for n, *_r in half:
            pg.d.text((pg.cx - mm(80), y), n["title"], font=F(SANSB, 10), fill=INK); y += mm(6)
            for which in ("crypto", "crypto2"):
                y = sub(pg.d, pg.cx).para(f"“{end_punct(n[which][0])}”", y, width=mm(160), font=(ITAL, 11.5), lead=mm(6.3)) + mm(1)
            y += mm(4)
    pg = new(); y = pg.head("Solutions", "Who said it?")
    for n, ws, key, cw, who in results:
        pg.d.text((pg.cx - mm(80), y), n["title"], font=F(SANSB, 10), fill=INK); y += mm(6)
        line = "   ".join(f"{i + 1}. {s}" for i, (_, s) in enumerate(who))
        y = sub(pg.d, pg.cx).para(line, y, width=mm(160), font=(SERIF, 11), lead=mm(6.2)) + mm(3)
    pg = new(); y = pg.head("Solutions", "Missing words, anagrams and quizzes")
    for n, ws2, ana, quiz in extra:
        pg.d.text((pg.cx - mm(80), y), n["title"], font=F(SANSB, 10), fill=INK); y += mm(6)
        miss = "   ".join(f"{i + 1}. {w}" for i, (_, w) in enumerate(n["missing"]))
        an = "   ".join(f"{i + 1}. {w.title()}" for i, (_, w) in enumerate(ana))
        qz = "   ".join(f"{i + 1}. {a}" for i, a in enumerate(quiz))
        for label, txt in (("Missing words", miss), ("Anagrams", an), ("Quiz", qz)):
            y = sub(pg.d, pg.cx).para(f"{label}:  {txt}", y, width=mm(160), font=(SERIF, 10.5), lead=mm(5.6)) - mm(1)
        y += mm(4)
    contents_page(contents, starts, sol_start)
    while len(pages) % 4:      # whole signatures look tidier; Lulu only needs an even count
        notes_page(new())
    for pg in pages[1:]:
        if pg.no > 4: pg.folio()
    return pages


if __name__ == "__main__":
    pages = build()
    print(len(pages), "pages")
    ims = [pg.im.convert("L") for pg in pages]      # black-and-white interior
    # sixteen shades of grey are plenty for black-and-white pages and keep the print file small
    ims = [im.point(lambda v: round(v / 17) * 17) for im in ims]
    import io, img2pdf
    pngs = []
    for im in ims:
        buf = io.BytesIO(); im.save(buf, "PNG", optimize=True, dpi=(DPI, DPI)); pngs.append(buf.getvalue())
    open("austen-interior.pdf", "wb").write(img2pdf.convert(pngs))
    for k in (0, 4, 5, 6, 7, 8, 9):
        ims[k].resize((637, 825)).save(f"prev-{k + 1:02d}.jpg", quality=85)
    for k in range(len(ims) - 9, len(ims)):
        ims[k].resize((637, 825)).save(f"prev-{k + 1:02d}.jpg", quality=85)
