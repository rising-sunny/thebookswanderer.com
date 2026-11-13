"""The 2027 Reading Challenge Journal: the kit's pages laid out for a printed A5 paperback (5.83 x 8.27 in, 56 pages).

Same artwork and prompts as the printable kit (build_kit.py), re-flowed for a small page: no overflowing columns,
two checklist pages, one review block per half page, and only embedded fonts (Lulu rejects the PDF base fonts).

  python build_journal.py FONTS_DIR OUT.pdf      # FONTS_DIR needs EBGaramond.ttf and EBGaramond-Italic.ttf
Karla (SIL OFL 1.1) comes from server/social/fonts in this repository.
"""
import random
import sys
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import build_kit as bk
from build_kit import GOLD, GREEN, INK, MONTHS, PROMPTS, RULE, SHELF, YEAR, HexColor, white

KARLA = Path(__file__).resolve().parents[2] / "server" / "social" / "fonts"
pdfmetrics.registerFont(TTFont("Sans", str(KARLA / "Karla-400.ttf")))
pdfmetrics.registerFont(TTFont("SansB", str(KARLA / "Karla-700.ttf")))
SIZE = (5.83 * 72, 8.27 * 72)          # Lulu 0583X0827: A5, no bleed
TITLE = f"The {YEAR} Reading Challenge Journal"
FONT_MAP = {"Helvetica": "Sans", "Helvetica-Bold": "SansB"}


class Journal(bk.Kit):
    def __init__(self, path):
        self.c = canvas.Canvas(str(path), pagesize=SIZE, initialFontName="Garamond", initialFontSize=10)
        self.c.setTitle(TITLE)
        self.c.setAuthor("The Books Wanderer")
        real = self.c.setFont
        self.c.setFont = lambda name, size, leading=None: real(FONT_MAP.get(name, name), size, leading)
        self.W, self.H = SIZE
        self.m = 0.55 * 72
        self.page_no = 0

    def frame(self, title=None, subtitle=None):
        c, W, H, m = self.c, self.W, self.H, self.m
        c.setFillColor(bk.PAPER); c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setStrokeColor(GOLD); c.setLineWidth(1.2); c.rect(m, m, W - 2 * m, H - 2 * m)
        c.setLineWidth(0.5); c.rect(m + 4, m + 4, W - 2 * m - 8, H - 2 * m - 8)
        self.top = H - m - 40
        if title:
            self.smallcaps(title, W / 2, self.top - 10, 20, GREEN, center=True)
            self.top -= 28
        if subtitle:
            c.setFont("GaramondIt", 10.5); c.setFillColor(INK)
            c.drawCentredString(W / 2, self.top - 4, subtitle)
            self.top -= 20
        self.page_no += 1
        c.setFont("Helvetica", 6.5); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, m + 12, f"{TITLE}  ·  The Books Wanderer  ·  {self.page_no}")

    # --- pages that need re-flowing for A5 ------------------------------------------------
    def cover(self):
        c, W, H = self.c, self.W, self.H
        self.frame()
        self.smallcaps("The", W / 2, H * 0.66, 20, GOLD, center=True)
        self.smallcaps(f"{YEAR} Reading", W / 2, H * 0.60, 32, GREEN, center=True)
        self.smallcaps("Challenge Journal", W / 2, H * 0.545, 24, GREEN, center=True)
        c.setFont("GaramondIt", 13); c.setFillColor(INK)
        c.drawCentredString(W / 2, H * 0.49, "Fifty-two books, one a week, none of them assigned.")
        x, y = W / 2 - 13 * 8, H * 0.32
        rnd = random.Random(7)
        for i in range(26):
            h = rnd.randint(40, 66)
            c.setFillColor(SHELF[i % len(SHELF)]); c.setStrokeColor(GOLD); c.setLineWidth(0.5)
            c.rect(x + i * 8, y, 7, h, stroke=1, fill=1)
        self.line(x - 6, y, x + 26 * 8 + 4, GOLD, 1)
        c.setFont("Helvetica", 7); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, H * 0.24, "TRACKER  ·  BINGO  ·  MONTHLY LOGS  ·  REVIEWS")
        c.setFont("Garamond", 11); c.setFillColor(GREEN)
        c.drawCentredString(W / 2, H * 0.19, "The Books Wanderer")
        self.done()

    def belongs(self):
        c, W = self.c, self.W
        self.frame()
        c.setFont("GaramondIt", 14); c.setFillColor(INK)
        c.drawCentredString(W / 2, self.H * 0.62, "This journal belongs to")
        self.line(W / 2 - 100, self.H * 0.62 - 34, W / 2 + 100)
        c.drawCentredString(W / 2, self.H * 0.50, "Year begun")
        self.line(W / 2 - 60, self.H * 0.50 - 30, W / 2 + 60)
        self.done()

    def how_to(self):
        c, W = self.c, self.W
        self.frame("How to use this journal", "Fill it in your own way. Nothing here is a deadline.")
        steps = [
            ("Pick a pace", "52 is the full challenge. 26 or 12 work just as well: choose the prompts you like and skip the rest."),
            ("Choose your next three", "Don't plan the year in January. Keep three prompts in mind and pick a book that fits one."),
            ("One book, one prompt", "A book can only tick one box, even if it fits several. That keeps the year varied."),
            ("Colour the shelf", "Each finished book fills one spine on the bookshelf tracker."),
            ("Play bingo with friends", "Four cards with different mixes of prompts. A line wins; a full card wins the year."),
            ("Log the month", "One page a month for titles, pages and stars."),
            ("Write it down", "Review pages for the books you want to remember, and lists for the next ones, without guilt."),
            ("Look back in December", "The year in books page turns your logs into a few numbers and a favourite."),
        ]
        x, maxw = self.m + 30, W - 2 * self.m - 60
        y = self.top - 14
        for i, (head, body) in enumerate(steps, 1):
            c.setFont("Garamond", 20); c.setFillColor(GOLD); c.drawString(x, y - 5, f"{i}")
            self.smallcaps(head, x + 26, y, 12, GREEN)
            c.setFont("Garamond", 10); c.setFillColor(INK)
            words, line, ly = body.split(), "", y - 14
            for w in words:
                t = (line + " " + w).strip()
                if pdfmetrics.stringWidth(t, "Garamond", 10) > maxw - 26:
                    c.drawString(x + 26, ly, line); line = w; ly -= 12
                else:
                    line = t
            c.drawString(x + 26, ly, line)
            y -= 47
        self.done()

    def checklist(self):
        for half in (0, 1):
            c, W = self.c, self.W
            self.frame(f"The {YEAR} Reading Challenge  ·  {half + 1} of 2",
                       "Tick a prompt when a book fits it and write the title on the line.")
            y0 = self.top - 16
            step = (y0 - self.m - 34) / 26
            x = self.m + 26
            col_w = W - 2 * self.m - 52
            for k in range(26):
                i = half * 26 + k
                p, y = PROMPTS[i], y0 - k * step
                c.setFont("Helvetica", 6.5); c.setFillColor(GOLD); c.drawRightString(x + 10, y, f"{i + 1:02d}")
                c.setStrokeColor(INK); c.setLineWidth(0.6); c.rect(x + 14, y - 1, 7, 7)
                c.setFont("Garamond", 9.2); c.setFillColor(INK); c.drawString(x + 27, y, p)
                tw = pdfmetrics.stringWidth(p, "Garamond", 9.2)
                self.line(x + 31 + tw, y - 1, x + col_w)
            self.done()

    def bingo(self, card, seed):
        c, W = self.c, self.W
        self.frame(f"Reading bingo  ·  card {card}", "Five in a row wins. Fill the card and you win the year.")
        rnd = random.Random(seed)
        picks = rnd.sample(PROMPTS, 24)
        picks.insert(12, "FREE: any book you love")
        size = W - 2 * self.m - 40
        cell = size / 5
        x0, y0 = (W - size) / 2, self.top - 22
        self.smallcaps("B   I   N   G   O", W / 2, y0 + 2, 18, GOLD, center=True)
        y0 -= 12
        for i, p in enumerate(picks):
            r, k = divmod(i, 5)
            x, y = x0 + k * cell, y0 - (r + 1) * cell
            free = i == 12
            c.setFillColor(HexColor("#efe7d2") if free else white); c.setStrokeColor(GOLD); c.setLineWidth(0.8)
            c.rect(x, y, cell, cell, stroke=1, fill=1)
            fs, lines, cur = 7.6, [], ""
            for wd in p.split():
                t = (cur + " " + wd).strip()
                if pdfmetrics.stringWidth(t, "Garamond", fs) > cell - 8:
                    lines.append(cur); cur = wd
                else:
                    cur = t
            lines.append(cur)
            c.setFont("Garamond", fs); c.setFillColor(GREEN if free else INK)
            ty = y + cell / 2 + (len(lines) - 1) * 4.4
            for ln in lines:
                c.drawCentredString(x + cell / 2, ty - 2, ln); ty -= 8.8
        self.done()

    def month(self, name):
        c, W = self.c, self.W
        self.frame(f"{name} {YEAR}", "What you read this month.")
        x1, x2 = self.m + 24, W - self.m - 24
        cols = [("Title", 0.0), ("Author", 0.35), ("No.", 0.57), ("Pages", 0.65), ("Rating", 0.73), ("Done", 0.94)]
        y = self.top - 14
        for t, f in cols:
            self.label(t, x1 + f * (x2 - x1), y, size=6.2)
        self.line(x1, y - 5, x2, GREEN, 0.9)
        step = 25
        for i in range(10):
            yy = y - 5 - (i + 1) * step
            self.line(x1, yy, x2)
            self.stars(x1 + 0.73 * (x2 - x1) + 3, yy + 8, s=3.4)
            c.setStrokeColor(INK); c.setLineWidth(0.6); c.rect(x1 + 0.94 * (x2 - x1) + 1, yy + 4, 7, 7)
        yb = y - 5 - 10 * step - 20
        bw = (x2 - x1 - 12) / 3
        for i, t in enumerate(["Books finished", "Pages read", "Best of the month"]):
            self.box(x1 + i * (bw + 6), yb - 44, bw, 44, title=t)
        self.box(x1, self.m + 30, x2 - x1, yb - 58 - self.m - 30, title="A line worth keeping")
        self.done()

    def reviews(self):
        c, W = self.c, self.W
        self.frame("Book reviews", "For the books you want to remember.")
        x1, x2 = self.m + 24, W - self.m - 24
        half = (self.top - self.m - 36) / 2
        for k in range(2):
            top = self.top - 6 - k * half
            self.label("Title", x1, top); self.line(x1 + 28, top - 2, x2)
            self.label("Author", x1, top - 20); self.line(x1 + 34, top - 22, x2)
            self.label("Prompt", x1, top - 40); self.line(x1 + 36, top - 42, x1 + 70)
            self.label("Started", x1 + 84, top - 40); self.line(x1 + 118, top - 42, x1 + 170)
            self.label("Finished", x1 + 184, top - 40); self.line(x1 + 222, top - 42, x2)
            self.label("Rating", x1, top - 60); self.stars(x1 + 40, top - 58, s=4.4)
            self.label("What stayed with me", x1, top - 82)
            self.ruled(x1, top - 86, x2 - x1, int((half - 100) / 19))
        self.done()

    def goals(self):
        self.frame(f"Before {YEAR} begins", "A few intentions. None of them is a deadline.")
        x1, x2 = self.m + 24, self.W - self.m - 24
        y = self.top - 8
        for t, n in [("How many books I'd like to read", 1), ("Prompts I'm looking forward to", 3),
                     ("Prompts that scare me a little", 3), ("Authors I want to discover", 3),
                     ("A book I keep putting off", 1), ("Where and when I like to read", 2),
                     ("One reading habit to build", 2)]:
            self.label(t, x1, y)
            y = self.ruled(x1, y - 4, x2 - x1, n, 17) - 17
        self.done()

    def year(self):
        self.frame("The year in books", "Fill this in at the end of December.")
        x1, x2 = self.m + 24, self.W - self.m - 24
        bw, bh = (x2 - x1 - 12) / 3, 42
        y = self.top - 8
        stats = ["Books finished", "Pages read", "Prompts ticked", "New authors", "Countries visited", "Did not finish",
                 "Longest book", "Shortest book", "Bingo lines"]
        for i, t in enumerate(stats):
            r, k = divmod(i, 3)
            self.box(x1 + k * (bw + 6), y - (r + 1) * (bh + 6), bw, bh, title=t)
        y -= 3 * (bh + 6) + 16
        self.label("Top five of the year", x1, y)
        for i in range(5):
            yy = y - 4 - (i + 1) * 19
            self.c.setFont("Garamond", 11); self.c.setFillColor(GOLD); self.c.drawString(x1, yy + 3, f"{i + 1}")
            self.line(x1 + 14, yy, x2)
        y = y - 4 - 5 * 19 - 18
        self.label("The book I'd hand to a friend, and why", x1, y)
        self.ruled(x1, y - 4, x2 - x1, max(2, int((y - self.m - 40) / 19)), 19)
        self.done()

    def notes(self, n):
        self.frame("Notes", "Anything that does not fit elsewhere.")
        x1, x2 = self.m + 24, self.W - self.m - 24
        self.ruled(x1, self.top - 6, x2 - x1, int((self.top - self.m - 40) / 21), 21)
        self.done()

    def list_page(self, title, subtitle, cols):
        super().list_page(title, subtitle, cols)

    def colophon(self):
        c, W = self.c, self.W
        self.frame()
        c.setFont("GaramondIt", 12); c.setFillColor(INK)
        c.drawCentredString(W / 2, self.H * 0.56, "Made for readers who like to keep count.")
        c.setFont("Garamond", 10.5); c.setFillColor(GREEN)
        c.drawCentredString(W / 2, self.H * 0.50, "The Books Wanderer")
        c.setFont("Garamond", 9); c.setFillColor(INK)
        c.drawCentredString(W / 2, self.H * 0.46, "thebookswanderer.com")
        self.done()

    def build(self):
        self.cover(); self.belongs(); self.how_to(); self.goals(); self.checklist(); self.shelf()
        for k, seed in zip("ABCD", (11, 22, 33, 44)):
            self.bingo(k, seed)
        for m in MONTHS:
            self.month(m)
        for _ in range(26):
            self.reviews()
        self.list_page("To be read", "The books waiting for their turn.", [("Title", 0.0), ("Author", 0.5), ("Prompt it fits", 0.78)])
        self.list_page("Did not finish", "No guilt. Just a note for next time.", [("Title", 0.0), ("Stopped at page", 0.45), ("Why", 0.72)])
        self.quotes(); self.year()
        self.notes(1); self.notes(2)
        self.colophon()
        self.c.save()


if __name__ == "__main__":
    out = Path(sys.argv[2])
    j = Journal(out)
    j.build()
    print(out, j.page_no, "pages")
