"""The 2027 Reading Challenge Kit: a printable PDF, US Letter and A4, for Etsy and the store.

  python build_kit.py   # writes reading-challenge-kit-2027-letter.pdf and -a4.pdf + preview PNGs

Fonts: EB Garamond (SIL OFL 1.1), Helvetica (built in). Same look as the free challenge PDF.
"""
import random
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Garamond", str(FONTS / "EBGaramond.ttf")))
pdfmetrics.registerFont(TTFont("GaramondIt", str(FONTS / "EBGaramond-Italic.ttf")))

GREEN, GOLD, INK, RULE, PAPER = (HexColor(c) for c in ("#233f33", "#9a7b3c", "#2a2622", "#c9bfae", "#ffffff"))
SHELF = [HexColor(c) for c in ("#e9d9c0", "#d8e2d6", "#e7cfc8", "#d6dbe6", "#efe4c6", "#dcd0e2")]
YEAR = "2027"
PROMPTS = [
    "Published the year you were born", "A classic you pretended to have read", "Set in a country you've never visited",
    "Under 200 pages", "Over 500 pages", "Translated from another language", "A debut novel", "Recommended by a friend",
    "Has a map inside", "Written by someone over 70", "Set in winter", "A book you own but never opened",
    "Chosen only by its cover", "A short-story collection", "Poetry", "Nonfiction about a place", "A mystery",
    "Set in a library or bookshop", "A book that became a film - read it first", "Written in letters or diaries",
    "Banned somewhere, once", "From the year 1927", "By an author who shares your initials",
    "Set on a train, a ship or a plane", "Its title is a question", "A book about food", "Set in summer",
    "Recommended on BookTok or Bookstagram", "A reread of a childhood favourite", "Published this year",
    "By a Nobel laureate", "A graphic novel", "A fairy tale retold", "Set in the city where you live", "A memoir",
    "A book a stranger was reading", "A colour in its title", "Fewer than 1,000 ratings online", "Science, explained",
    "A play", "The first in a series", "Set more than 200 years ago", "Set in the future", "From a used bookshop",
    "Gifted to you", "Its author died before you were born", "A book about books", "Has an animal on the cover",
    "Read in a single day", "Picked from the library at random", "A book you'll gift to someone afterwards",
    "The one you've been saving",
]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
assert len(PROMPTS) == 52


class Kit:
    def __init__(self, path, size):
        self.c = canvas.Canvas(str(path), pagesize=size)
        self.c.setTitle("The 2027 Reading Challenge Kit")
        self.c.setAuthor("The Books Wanderer")
        self.W, self.H = size
        self.m = 0.55 * 72                       # outer margin
        self.page_no = 0

    # --- page furniture -------------------------------------------------------------
    def frame(self, title=None, subtitle=None):
        c, W, H, m = self.c, self.W, self.H, self.m
        c.setFillColor(PAPER); c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setStrokeColor(GOLD); c.setLineWidth(1.2); c.rect(m, m, W - 2 * m, H - 2 * m)
        c.setLineWidth(0.5); c.rect(m + 4, m + 4, W - 2 * m - 8, H - 2 * m - 8)
        self.top = H - m - 40
        if title:
            self.smallcaps(title, W / 2, self.top - 10, 24, GREEN, center=True)
            self.top -= 30
        if subtitle:
            c.setFont("GaramondIt", 11.5); c.setFillColor(INK)
            c.drawCentredString(W / 2, self.top - 4, subtitle)
            self.top -= 22
        self.page_no += 1
        c.setFont("Helvetica", 6.5); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, m + 12, f"The 2027 Reading Challenge Kit  ·  The Books Wanderer  ·  for personal use  ·  {self.page_no}")

    def done(self):
        self.c.showPage()

    def smallcaps(self, text, x, y, size, color, center=False):
        """Small caps in EB Garamond: capitals full size, other letters as smaller capitals."""
        c = self.c
        parts, w = [], 0
        for ch in text:
            big = ch.isupper() or not ch.isalpha()
            f = size if big else size * 0.78
            parts.append((ch.upper(), f)); w += pdfmetrics.stringWidth(ch.upper(), "Garamond", f)
        x0 = x - w / 2 if center else x
        c.setFillColor(color)
        for ch, f in parts:
            c.setFont("Garamond", f); c.drawString(x0, y, ch); x0 += pdfmetrics.stringWidth(ch, "Garamond", f)

    def label(self, text, x, y, color=GOLD, size=6.8):
        self.c.setFont("Helvetica-Bold", size); self.c.setFillColor(color); self.c.drawString(x, y, text.upper())

    def line(self, x1, y, x2, color=RULE, w=0.6):
        self.c.setStrokeColor(color); self.c.setLineWidth(w); self.c.line(x1, y, x2, y)

    def box(self, x, y, w, h, r=6, title=None):
        c = self.c
        c.setStrokeColor(GOLD); c.setLineWidth(0.7); c.roundRect(x, y, w, h, r)
        if title:
            self.label(title, x + 8, y + h - 13)

    def stars(self, x, y, n=5, s=4.2):
        c = self.c
        c.setStrokeColor(GOLD); c.setLineWidth(0.6)
        import math
        for i in range(n):
            cx = x + i * (2.6 * s)
            pts = []
            for k in range(10):
                r = s if k % 2 == 0 else s * 0.45
                a = math.pi / 2 + k * math.pi / 5
                pts.append((cx + r * math.cos(a), y + r * math.sin(a)))
            p = c.beginPath(); p.moveTo(*pts[0])
            for q in pts[1:]:
                p.lineTo(*q)
            p.close(); c.drawPath(p, stroke=1, fill=0)

    def ruled(self, x, y_top, w, n, step=19):
        for i in range(n):
            self.line(x, y_top - (i + 1) * step, x + w)
        return y_top - n * step

    # --- pages ------------------------------------------------------------------------
    def cover(self):
        c, W, H = self.c, self.W, self.H
        self.frame()
        self.smallcaps("The", W / 2, H * 0.64, 22, GOLD, center=True)
        self.smallcaps(f"{YEAR} Reading Challenge", W / 2, H * 0.58, 34, GREEN, center=True)
        self.smallcaps("Kit", W / 2, H * 0.52, 30, GREEN, center=True)
        c.setFont("GaramondIt", 14); c.setFillColor(INK)
        c.drawCentredString(W / 2, H * 0.46, "Fifty-two books, one a week, none of them assigned.")
        # a small row of spines
        x, y = W / 2 - 13 * 9, H * 0.30
        rnd = random.Random(7)
        for i in range(26):
            h = rnd.randint(42, 70)
            c.setFillColor(SHELF[i % len(SHELF)]); c.setStrokeColor(GOLD); c.setLineWidth(0.5)
            c.rect(x + i * 9, y, 8, h, stroke=1, fill=1)
        self.line(x - 6, y, x + 26 * 9 + 4, GOLD, 1)
        c.setFont("Helvetica", 8); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, H * 0.22, "TRACKER  ·  BINGO  ·  MONTHLY LOGS  ·  REVIEWS  ·  YEAR IN BOOKS")
        c.setFont("Garamond", 11); c.setFillColor(GREEN)
        c.drawCentredString(W / 2, H * 0.17, "The Books Wanderer")
        self.done()

    def how_to(self):
        c, W = self.c, self.W
        self.frame("How to use this kit", "Print what you need, as many times as you need it.")
        steps = [
            ("Pick a pace", "52 is the full challenge. 26 or 12 work just as well: choose the prompts you like and skip the rest."),
            ("Choose your next three", "Don't plan the whole year in January. Keep three prompts in mind and pick a book that fits one."),
            ("One book, one prompt", "A book can only tick one box, even if it fits several. That keeps the year varied."),
            ("Colour the shelf", "Each finished book fills one spine on the bookshelf tracker. Use any colour you like."),
            ("Play bingo with friends", "Four bingo cards with different mixes of prompts. A line wins; a full card wins the year."),
            ("Log the month", "One page a month for titles, pages and stars, plus a quote worth keeping."),
            ("Write it down", "Review pages for the books you want to remember, a TBR list and a DNF list without guilt."),
            ("Look back in December", "The year in books page turns your logs into a few numbers and a favourite."),
        ]
        y, x = self.top - 20, self.m + 40
        for i, (head, body) in enumerate(steps, 1):
            c.setFont("Garamond", 22); c.setFillColor(GOLD); c.drawString(x, y - 6, f"{i}")
            self.smallcaps(head, x + 30, y, 13, GREEN)
            c.setFont("Garamond", 10.5); c.setFillColor(INK)
            c.drawString(x + 30, y - 15, body[:95])
            if len(body) > 95:
                c.drawString(x + 30, y - 28, body[95:].strip())
            y -= 56
        c.setFont("GaramondIt", 10); c.setFillColor(INK)
        c.drawCentredString(W / 2, self.m + 40, "Prints well on plain paper. Also works in GoodNotes, Notability or any PDF app on a tablet.")
        self.done()

    def checklist(self):
        c, W = self.c, self.W
        self.frame(f"The {YEAR} Reading Challenge", "Tick a prompt when a book fits it and write the title on the line.")
        col_w = (W - 2 * self.m - 60) / 2
        y0 = self.top - 14
        step = (y0 - self.m - 34) / 26
        for i, p in enumerate(PROMPTS):
            col, row = divmod(i, 26)
            x = self.m + 26 + col * (col_w + 12)
            y = y0 - row * step
            c.setFont("Helvetica", 6.5); c.setFillColor(GOLD); c.drawRightString(x + 10, y, f"{i + 1:02d}")
            c.setStrokeColor(INK); c.setLineWidth(0.6); c.rect(x + 14, y - 1, 7, 7)
            c.setFont("Garamond", 8.8); c.setFillColor(INK); c.drawString(x + 26, y, p)
            tw = pdfmetrics.stringWidth(p, "Garamond", 8.8)
            self.line(x + 30 + tw, y - 1, x + col_w)
        self.done()

    def shelf(self):
        c, W = self.c, self.W
        self.frame("The bookshelf tracker", "Colour one spine for every book you finish. The number is its prompt.")
        rows, per = 4, 13
        shelf_w = W - 2 * self.m - 70
        spine_w = shelf_w / per - 4
        y_top = self.top - 30
        row_h = (y_top - self.m - 60) / rows
        rnd = random.Random(2027)
        n = 0
        for r in range(rows):
            base = y_top - (r + 1) * row_h + 10
            x0 = self.m + 35
            for k in range(per):
                n += 1
                h = row_h * rnd.uniform(0.62, 0.86)
                x = x0 + k * (spine_w + 4)
                c.setFillColor(white); c.setStrokeColor(INK); c.setLineWidth(0.7)
                c.rect(x, base, spine_w, h, stroke=1, fill=1)
                c.setStrokeColor(RULE); c.setLineWidth(0.4)
                c.line(x + 2, base + h - 8, x + spine_w - 2, base + h - 8)
                c.line(x + 2, base + 8, x + spine_w - 2, base + 8)
                c.setFont("Helvetica", 6.5); c.setFillColor(GOLD)
                c.drawCentredString(x + spine_w / 2, base + 2, f"{n:02d}")
            c.setStrokeColor(GOLD); c.setLineWidth(2.2)
            c.line(self.m + 28, base - 1, W - self.m - 28, base - 1)
        self.done()

    def bingo(self, card, seed):
        c, W = self.c, self.W
        self.frame(f"Reading bingo  ·  card {card}", "Five in a row wins. Fill the whole card and you win the year.")
        rnd = random.Random(seed)
        picks = rnd.sample(PROMPTS, 24)
        picks.insert(12, "FREE: any book you love")
        size = min(W - 2 * self.m - 60, self.top - self.m - 70)
        cell = size / 5
        x0 = (W - size) / 2
        y0 = self.top - 20
        self.smallcaps("B   I   N   G   O", W / 2, y0 + 2, 20, GOLD, center=True)
        y0 -= 12
        for i, p in enumerate(picks):
            r, k = divmod(i, 5)
            x, y = x0 + k * cell, y0 - (r + 1) * cell
            free = i == 12
            c.setFillColor(HexColor("#efe7d2") if free else white); c.setStrokeColor(GOLD); c.setLineWidth(0.8)
            c.rect(x, y, cell, cell, stroke=1, fill=1)
            words, lines, cur = p.split(), [], ""
            fs = 9 if not free else 9.5
            for wd in words:
                t = (cur + " " + wd).strip()
                if pdfmetrics.stringWidth(t, "Garamond", fs) > cell - 12:
                    lines.append(cur); cur = wd
                else:
                    cur = t
            lines.append(cur)
            c.setFont("Garamond", fs); c.setFillColor(GREEN if free else INK)
            ty = y + cell / 2 + (len(lines) - 1) * 5.5
            for ln in lines:
                c.drawCentredString(x + cell / 2, ty, ln); ty -= 11
        self.done()

    def month(self, name):
        c, W = self.c, self.W
        self.frame(f"{name} {YEAR}", "What you read this month.")
        x1, x2 = self.m + 26, W - self.m - 26
        cols = [("Title", 0.0), ("Author", 0.36), ("Prompt", 0.58), ("Pages", 0.67), ("Rating", 0.76), ("Done", 0.92)]
        y = self.top - 16
        for t, f in cols:
            self.label(t, x1 + f * (x2 - x1), y)
        self.line(x1, y - 5, x2, GREEN, 0.9)
        step = 24
        for i in range(10):
            yy = y - 5 - (i + 1) * step
            self.line(x1, yy, x2)
            self.stars(x1 + 0.76 * (x2 - x1) + 4, yy + 8)
            c.setStrokeColor(INK); c.setLineWidth(0.6); c.rect(x1 + 0.92 * (x2 - x1) + 6, yy + 4, 8, 8)
        yb = y - 5 - 10 * step - 22
        bw = (x2 - x1 - 16) / 3
        for i, t in enumerate(["Books finished", "Pages read", "Best of the month"]):
            self.box(x1 + i * (bw + 8), yb - 48, bw, 48, title=t)
        self.box(x1, self.m + 30, x2 - x1, yb - 64 - self.m - 30, title="A line worth keeping")
        self.done()

    def reviews(self):
        c, W = self.c, self.W
        self.frame("Book reviews", "For the books you want to remember.")
        x1, x2 = self.m + 26, W - self.m - 26
        half = (self.top - self.m - 40) / 2
        for k in range(2):
            top = self.top - 6 - k * half
            for j, (t, f) in enumerate([("Title", 0.0), ("Author", 0.55)]):
                self.label(t, x1 + f * (x2 - x1), top)
                self.line(x1 + f * (x2 - x1) + 40, top - 2, x1 + (0.52 if j == 0 else 1.0) * (x2 - x1))
            self.label("Prompt", x1, top - 22); self.line(x1 + 44, top - 24, x1 + 90)
            self.label("Started", x1 + 110, top - 22); self.line(x1 + 152, top - 24, x1 + 230)
            self.label("Finished", x1 + 245, top - 22); self.line(x1 + 292, top - 24, x1 + 370)
            self.stars(x2 - 60, top - 18)
            self.label("What stayed with me", x1, top - 46)
            self.ruled(x1, top - 50, x2 - x1, int((half - 80) / 19))
        self.done()

    def list_page(self, title, subtitle, cols):
        c, W = self.c, self.W
        self.frame(title, subtitle)
        x1, x2 = self.m + 26, W - self.m - 26
        y = self.top - 16
        for t, f in cols:
            self.label(t, x1 + f * (x2 - x1), y)
        self.line(x1, y - 5, x2, GREEN, 0.9)
        n = int((y - 5 - self.m - 30) / 21)
        for i in range(n):
            yy = y - 5 - (i + 1) * 21
            self.line(x1, yy, x2)
            c.setStrokeColor(INK); c.setLineWidth(0.6); c.rect(x1 - 14, yy + 5, 7, 7)
        self.done()

    def quotes(self):
        self.frame("Lines worth keeping", "The sentences you underlined, and where you found them.")
        x1, x2 = self.m + 26, self.W - self.m - 26
        h = (self.top - self.m - 40) / 6
        for i in range(6):
            y = self.top - 6 - (i + 1) * h
            self.box(x1, y + 6, x2 - x1, h - 10)
            self.label("from", x2 - 150, y + 14); self.line(x2 - 125, y + 13, x2 - 10)
        self.done()

    def goals(self):
        c = self.c
        self.frame(f"Before {YEAR} begins", "A few intentions. None of them is a deadline.")
        x1, x2 = self.m + 26, self.W - self.m - 26
        y = self.top - 10
        for t, n in [("How many books I'd like to read", 1), ("Prompts I'm looking forward to", 3),
                     ("Prompts that scare me a little", 3), ("Authors I want to discover", 3),
                     ("A book I keep putting off", 1), ("Where and when I like to read", 2),
                     ("One reading habit to build", 2)]:
            self.label(t, x1, y)
            y = self.ruled(x1, y - 4, x2 - x1, n, 20) - 22
        self.done()

    def year(self):
        self.frame(f"The year in books", "Fill this in at the end of December.")
        x1, x2 = self.m + 26, self.W - self.m - 26
        bw, bh = (x2 - x1 - 16) / 3, 56
        y = self.top - 10
        stats = ["Books finished", "Pages read", "Prompts ticked", "New authors", "Countries visited", "Did not finish",
                 "Longest book", "Shortest book", "Bingo lines"]
        for i, t in enumerate(stats):
            r, k = divmod(i, 3)
            self.box(x1 + k * (bw + 8), y - (r + 1) * (bh + 8), bw, bh, title=t)
        y -= 3 * (bh + 8) + 20
        self.label("Top five of the year", x1, y)
        for i in range(5):
            yy = y - 6 - (i + 1) * 22
            self.c.setFont("Garamond", 12); self.c.setFillColor(GOLD); self.c.drawString(x1, yy + 3, f"{i + 1}")
            self.line(x1 + 16, yy, x2)
        y = y - 6 - 5 * 22 - 22
        self.label("The book I'd hand to a friend, and why", x1, y)
        self.ruled(x1, y - 4, x2 - x1, max(2, int((y - self.m - 40) / 20)), 20)
        self.done()

    def build(self):
        self.cover(); self.how_to(); self.goals(); self.checklist(); self.shelf()
        for k, seed in zip("ABCD", (11, 22, 33, 44)):
            self.bingo(k, seed)
        for m in MONTHS:
            self.month(m)
        self.reviews(); self.reviews()
        self.list_page("To be read", "The books waiting for their turn.", [("Title", 0.0), ("Author", 0.5), ("Prompt it fits", 0.8)])
        self.list_page("Did not finish", "No guilt. Just a note for next time.", [("Title", 0.0), ("Stopped at page", 0.5), ("Why", 0.7)])
        self.quotes(); self.year()
        self.c.save()


if __name__ == "__main__":
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    for name, size in (("letter", letter), ("a4", A4)):
        k = Kit(out / f"reading-challenge-kit-{YEAR}-{name}.pdf", size)
        k.build()
        print(name, k.page_no, "pages")
