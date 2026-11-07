"""Pride and Prejudice Watch-Along & Read-Along Kit: a printable PDF, US Letter and A4.

  python build_kit.py <fonts_dir>   # writes out/pride-prejudice-watch-kit-letter.pdf and -a4.pdf

Reuses the page furniture of the 2027 Reading Challenge Kit (design/reading-challenge-kit).
Pride and Prejudice (1813) is in the public domain; every quotation below is from the novel.
The kit is independent and is not connected to any film or series.
"""
import importlib.util
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("rck", HERE.parent / "reading-challenge-kit" / "build_kit.py")
rck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rck)
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfbase import pdfmetrics

GREEN, GOLD, INK, RULE = rck.GREEN, rck.GOLD, rck.INK, rck.RULE
PAPER_TINT = HexColor("#f4ecda")

PLAN = [
    ("Volume I", "1 to 8", "Chapter 1: the famous first line. Chapter 3: the Meryton assembly."),
    ("Volume I", "9 to 16", "Chapter 13: Mr Collins's letter. Chapter 16: Wickham's story."),
    ("Volume I", "17 to 23", "Chapter 18: the Netherfield ball. Chapter 19: Mr Collins proposes."),
    ("Volume II", "24 to 29", "Chapters 28 and 29: Hunsford and dinner at Rosings."),
    ("Volume II", "30 to 35", "Chapter 34: the first proposal. Chapter 35: the letter."),
    ("Volume II", "36 to 42", "Chapter 36: “Till this moment I never knew myself.”"),
    ("Volume III", "43 to 49", "Chapter 43: Pemberley. Chapter 46: the news about Lydia."),
    ("Volume III", "50 to 55", "Chapter 55: Bingley and Jane."),
    ("Volume III", "56 to 61", "Chapter 56: Lady Catherine's visit. Chapter 58: the second proposal."),
]

WHOS_WHO = [
    ("Elizabeth Bennet", "The second Bennet daughter. Quick, witty, sure of her own judgement."),
    ("Jane Bennet", "The eldest. Gentle, and sees the good in everyone."),
    ("Mary Bennet", "The middle sister. Studious, fond of moral remarks."),
    ("Kitty Bennet", "The fourth sister, who follows Lydia's lead."),
    ("Lydia Bennet", "The youngest. Lively, careless, fond of officers."),
    ("Mr Bennet", "Their father. Dry-humoured, retreats to his library."),
    ("Mrs Bennet", "Their mother. Determined to see her daughters married."),
    ("Mr Darcy", "A wealthy landowner with Pemberley in Derbyshire. Proud, reserved."),
    ("Mr Bingley", "Darcy's cheerful friend, who rents Netherfield."),
    ("Caroline Bingley", "Bingley's sister. Has designs on Darcy."),
    ("Mr Wickham", "An officer in the militia. Charming, with a story about Darcy."),
    ("Mr Collins", "A clergyman and the Bennets' cousin, who will inherit Longbourn."),
    ("Charlotte Lucas", "Elizabeth's practical friend and neighbour."),
    ("Lady Catherine de Bourgh", "Darcy's domineering aunt, at Rosings Park."),
    ("Colonel Fitzwilliam", "Darcy's cousin, a soldier."),
    ("Georgiana Darcy", "Darcy's much younger sister. Shy."),
    ("The Gardiners", "Mrs Bennet's brother and his wife. Kind and sensible."),
]

MOMENTS = [
    "A letter is read aloud", "Mrs Bennet and her nerves", "A walk across muddy fields", "Mr Bennet hides in the library",
    "Lady Catherine disapproves", "Mr Collins is pleased with himself", "A ball at Netherfield", "Darcy watches Elizabeth",
    "Someone says “tolerable”", "Caroline Bingley sneers", "Wickham tells his story", "A proposal goes badly",
    "Darcy writes a letter", "A visit to Pemberley", "Lydia runs off", "Jane falls ill at Netherfield",
    "Someone plays the pianoforte", "Awkward conversation while dancing", "Mary performs when nobody asked",
    "Bingley leaves suddenly", "Elizabeth refuses a proposal", "Gossip in Meryton", "Wickham flirts",
    "Mr Bingley is delighted with everyone", "Elizabeth laughs at Darcy", "Rain, and somebody gets wet",
    "Officers in red coats", "A secret is kept", "Elizabeth stands up to Lady Catherine", "An apology is made",
    "Darcy looks uncomfortable", "A sister gives advice", "Someone mentions a fortune", "A carriage arrives at a bad moment",
    "Lydia is the loudest in the room", "Charlotte accepts Mr Collins", "Mr Darcy is rude at a party",
    "A change of heart", "Mrs Bennet matchmakes",
]

QUOTES = [
    ("It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.", "The narrator, chapter 1"),
    ("She is tolerable; but not handsome enough to tempt me.", "Mr Darcy"),
    ("I could easily forgive his pride, if he had not mortified mine.", "Elizabeth"),
    ("My good opinion once lost, is lost for ever.", "Mr Darcy"),
    ("A lady's imagination is very rapid; it jumps from admiration to love, from love to matrimony in a moment.", "Mr Darcy"),
    ("Vanity and pride are different things, though the words are often used synonymously.", "Mary"),
    ("I declare after all there is no enjoyment like reading!", "Caroline Bingley"),
    ("In vain have I struggled. It will not do. My feelings will not be repressed. You must allow me to tell you how ardently I admire and love you.", "Mr Darcy"),
    ("The more I see of the world, the more am I dissatisfied with it.", "Elizabeth"),
    ("Till this moment I never knew myself.", "Elizabeth"),
    ("For what do we live, but to make sport for our neighbours, and laugh at them in our turn?", "Mr Bennet"),
    ("My affections and wishes are unchanged.", "Mr Darcy"),
]
# Austen wrote "for ever" in the 1813 text; kept as is.

SCENES = [
    "The first line", "The Meryton assembly", "Mr Collins proposes", "Wickham's story", "Darcy's first proposal",
    "Darcy's letter", "Pemberley", "Lydia runs away", "Lady Catherine's visit to Longbourn", "Darcy's second proposal",
    "Jane and Bingley", "The ending",
]

WORDS = [
    ("Entail", "A legal arrangement that passes an estate to a male heir. Longbourn is entailed, so after Mr Bennet it goes to Mr Collins, which is why the daughters must marry."),
    ("A living", "A clergyman's post and income, given by a patron. Lady Catherine gave Mr Collins his."),
    ("An assembly", "A public ball open to the neighbourhood. Darcy and Elizabeth first meet at one in Meryton."),
    ("The militia", "A regiment stationed near Meryton for the winter. The officers' red coats fascinate the younger Bennet girls."),
    ("“A year”", "Income was quoted per year. Darcy is said to have ten thousand a year, Bingley four or five thousand."),
    ("Connexions", "Family and social connections. In this world they count for as much as money."),
    ("An express", "A letter carried by a special messenger instead of the ordinary post, for news that cannot wait."),
    ("A morning call", "A formal social visit paid during the day, not in the evening."),
    ("Gretna Green", "A Scottish village where couples could marry without parental consent. A runaway pair was often assumed to be heading there."),
]
PLACES = [("Longbourn", "the Bennets' home"), ("Netherfield", "the house Bingley rents"), ("Meryton", "the nearby market town"),
          ("Pemberley", "Darcy's estate in Derbyshire"), ("Rosings Park", "Lady Catherine's estate"), ("Hunsford", "Mr Collins's parsonage")]

QUESTIONS = [
    "Which first impression did you get wrong, and why?",
    "Is Darcy's first proposal an insult, a confession, or both?",
    "Charlotte Lucas marries Mr Collins for security. Is her choice sensible, sad, or both?",
    "Which sister would you swap places with for a day?",
    "How much of the plot depends on a letter?",
    "What does Wickham's charm hide, and who saw through it first?",
    "Mr Bennet is funny, and he also lets his daughters down. Do you forgive him?",
    "What would be missing from the story if there were no entail?",
    "Who changes more by the end, Elizabeth or Darcy?",
    "Which scene changed most between the book and the screen? Better or worse?",
    "Which line would you put on a tote bag?",
    "Whose side of an argument do you take, and does it ever change?",
]


def wrap(text, font, size, width):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(t, font, size) > width and cur:
            out.append(cur); cur = w
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


class PP(rck.Kit):
    def __init__(self, path, size):
        super().__init__(path, size)
        self.c.setTitle("Pride and Prejudice Watch-Along & Read-Along Kit")

    def frame(self, title=None, subtitle=None):
        c, W, H, m = self.c, self.W, self.H, self.m
        c.setFillColor(white); c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setStrokeColor(GOLD); c.setLineWidth(1.2); c.rect(m, m, W - 2 * m, H - 2 * m)
        c.setLineWidth(0.5); c.rect(m + 4, m + 4, W - 2 * m - 8, H - 2 * m - 8)
        self.top = H - m - 40
        if title:
            self.smallcaps(title, W / 2, self.top - 10, 24, GREEN, center=True); self.top -= 30
        if subtitle:
            c.setFont("GaramondIt", 11.5); c.setFillColor(INK)
            c.drawCentredString(W / 2, self.top - 4, subtitle); self.top -= 22
        self.page_no += 1
        c.setFont("Helvetica", 6.5); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, m + 12, f"Pride and Prejudice Watch-Along & Read-Along Kit  ·  The Books Wanderer  ·  for personal use  ·  {self.page_no}")

    def checkbox(self, x, y, s=7):
        self.c.setStrokeColor(INK); self.c.setLineWidth(0.6); self.c.rect(x, y, s, s)

    # --- pages -------------------------------------------------------------------------
    def cover(self):
        c, W, H = self.c, self.W, self.H
        self.frame()
        # a sealed letter
        lw, lh = 190, 118
        x, y = W / 2 - lw / 2, H * 0.60
        c.setFillColor(PAPER_TINT); c.setStrokeColor(GOLD); c.setLineWidth(1)
        c.rect(x, y, lw, lh, stroke=1, fill=1)
        c.line(x, y + lh, x + lw / 2, y + lh * 0.42); c.line(x + lw, y + lh, x + lw / 2, y + lh * 0.42)
        c.line(x, y, x + lw * 0.36, y + lh * 0.52); c.line(x + lw, y, x + lw * 0.64, y + lh * 0.52)
        c.setFillColor(HexColor("#7d2a22")); c.setStrokeColor(HexColor("#5c1d17")); c.circle(x + lw / 2, y + lh * 0.42, 15, stroke=1, fill=1)
        c.setFont("GaramondIt", 13); c.setFillColor(HexColor("#f0d9b8")); c.drawCentredString(x + lw / 2, y + lh * 0.42 - 4, "P&P")
        self.smallcaps("Pride and Prejudice", W / 2, H * 0.50, 34, GREEN, center=True)
        self.smallcaps("Watch-Along & Read-Along Kit", W / 2, H * 0.455, 18, GOLD, center=True)
        c.setFont("GaramondIt", 14); c.setFillColor(INK)
        c.drawCentredString(W / 2, H * 0.40, "Read it. Watch it. Argue about it over tea.")
        c.setFont("Helvetica", 8); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, H * 0.27, "READING PLAN  ·  EPISODE NOTES  ·  WHO'S WHO  ·  BINGO  ·  QUOTES  ·  WATCH PARTY")
        c.setFont("Garamond", 11); c.setFillColor(GREEN)
        c.drawCentredString(W / 2, H * 0.20, "The Books Wanderer")
        self.done()

    def how_to(self):
        c, W = self.c, self.W
        self.frame("How to use this kit", "For the book, for any film or series, or for both.")
        steps = [
            ("Read along", "Nine weeks, about seven chapters a week. Start on any date: it counts weeks, not dates."),
            ("Watch along", "Fill in an episode page as you watch. Print more if the story runs long."),
            ("Know who is who", "The cast page keeps the cousins and the Bingleys straight, with room for your first impressions."),
            ("Listen for the lines", "Twelve sentences from the novel to tick off when you hear them."),
            ("Play bingo", "Four cards of moments from the book. An adaptation may skip some, which makes the game harder."),
            ("Compare", "Book against screen, scene by scene. Pick a side and defend it."),
            ("Host a watch party", "A planning page, a vocabulary page and twelve questions for the sofa."),
        ]
        y, x = self.top - 22, self.m + 40
        for i, (head, body) in enumerate(steps, 1):
            c.setFont("Garamond", 22); c.setFillColor(GOLD); c.drawString(x, y - 6, f"{i}")
            self.smallcaps(head, x + 30, y, 13, GREEN)
            c.setFont("Garamond", 10.5); c.setFillColor(INK)
            for j, ln in enumerate(wrap(body, "Garamond", 10.5, W - 2 * self.m - 110)):
                c.drawString(x + 30, y - 15 - j * 13, ln)
            y -= 58
        c.setFont("GaramondIt", 9.5); c.setFillColor(INK)
        for j, ln in enumerate(["This kit is independent and is not connected to any film or series.",
                                "Pride and Prejudice was published in 1813; every quotation here is from the novel.",
                                "Prints well on plain paper. Also works in GoodNotes, Notability or any PDF app."]):
            c.drawCentredString(W / 2, self.m + 52 - j * 13, ln)
        self.done()

    def read_plan(self):
        c, W = self.c, self.W
        self.frame("The reading plan", "Sixty-one chapters in nine weeks. Tick each week when you finish it.")
        x1, x2 = self.m + 26, W - self.m - 26
        y = self.top - 14
        cols = [("Week", 0.0), ("Volume", 0.09), ("Chapters", 0.23), ("Look out for", 0.36), ("Done", 0.93)]
        for t, f in cols:
            self.label(t, x1 + f * (x2 - x1), y)
        self.line(x1, y - 5, x2, GREEN, 0.9)
        step = (y - self.m - 90) / 9
        for i, (vol, ch, note) in enumerate(PLAN, 1):
            yy = y - 5 - i * step
            self.line(x1, yy, x2)
            c.setFont("Garamond", 20); c.setFillColor(GOLD); c.drawString(x1, yy + step / 2 - 6, f"{i}")
            c.setFont("Garamond", 11); c.setFillColor(INK)
            c.drawString(x1 + 0.09 * (x2 - x1), yy + step / 2 - 4, vol)
            c.setFont("Garamond", 12); c.setFillColor(GREEN)
            c.drawString(x1 + 0.23 * (x2 - x1), yy + step / 2 - 4, ch)
            c.setFont("Garamond", 10.3); c.setFillColor(INK)
            lines = wrap(note, "Garamond", 10.3, 0.55 * (x2 - x1))
            for j, ln in enumerate(lines):
                c.drawString(x1 + 0.36 * (x2 - x1), yy + step / 2 + 2 - j * 12, ln)
            self.checkbox(x1 + 0.94 * (x2 - x1), yy + step / 2 - 6, 9)
        c.setFont("GaramondIt", 9); c.setFillColor(INK)
        for j, ln in enumerate(["Chapter numbers follow the usual edition of 61 chapters. Some editions number each volume separately,",
                                "from I.1 to III.19. Volume I has 23 chapters, Volume II has 19 and Volume III has 19."]):
            c.drawCentredString(W / 2, self.m + 40 - j * 12, ln)
        self.done()

    def episodes(self, first):
        c, W = self.c, self.W
        self.frame("Episode notes", "One block per episode, or per film. Print more pages if you need them.")
        x1, x2 = self.m + 26, W - self.m - 26
        n = 4
        bh = (self.top - self.m - 38) / n
        ticks = ["a letter", "a ball or a dance", "a long walk", "rain or mud", "a proposal", "Pemberley", "Lady Catherine", "Mr Collins"]
        for k in range(n):
            top = self.top - 6 - k * bh
            self.box(x1, top - bh + 8, x2 - x1, bh - 10)
            self.label(f"Episode", x1 + 10, top - 12); self.line(x1 + 46, top - 13, x1 + 90)
            self.label("Date", x1 + 104, top - 12); self.line(x1 + 126, top - 13, x1 + 205)
            self.stars(x2 - 66, top - 11)
            for j, lab in enumerate(["Best scene", "Best line", "Not like the book"]):
                yy = top - 32 - j * 17
                self.label(lab, x1 + 10, yy); self.line(x1 + 86, yy - 2, x2 - 10)
            c.setFont("Garamond", 9); c.setFillColor(INK)
            for j, t in enumerate(ticks):
                col, row = divmod(j, 2)
                tx = x1 + 10 + col * ((x2 - x1 - 20) / 4)
                ty = top - 88 - row * 15
                self.checkbox(tx, ty - 1, 6.5); c.drawString(tx + 11, ty, t)
        self.done()

    def whos_who(self):
        c, W = self.c, self.W
        self.frame("Who is who", "Jot down your first impression, then check it against how things turn out.")
        x1, x2 = self.m + 20, W - self.m - 20
        y = self.top - 8
        self.label("Character", x1, y); self.label("First impression", x1 + 0.50 * (x2 - x1), y)
        self.label("Did I change my mind?", x1 + 0.76 * (x2 - x1), y)
        self.line(x1, y - 5, x2, GREEN, 0.9)
        step = (y - self.m - 30) / len(WHOS_WHO)
        for i, (name, desc) in enumerate(WHOS_WHO, 1):
            yy = y - 5 - i * step
            self.line(x1, yy, x2)
            c.setFont("Garamond", 10.5); c.setFillColor(GREEN); c.drawString(x1, yy + step - 12, name)
            c.setFont("GaramondIt", 7.8); c.setFillColor(INK)
            for j, ln in enumerate(wrap(desc, "GaramondIt", 7.8, 0.47 * (x2 - x1))[:2]):
                c.drawString(x1, yy + step - 21 - j * 9, ln)
            self.line(x1 + 0.50 * (x2 - x1), yy + 5, x1 + 0.73 * (x2 - x1), RULE, 0.4)
            self.line(x1 + 0.76 * (x2 - x1), yy + 5, x2, RULE, 0.4)
        self.done()

    def moments_bingo(self, card, seed):
        c, W = self.c, self.W
        self.frame(f"Watch-along bingo  ·  card {card}", "Five in a row wins. The squares come from the book, so an adaptation may skip some.")
        rnd = random.Random(seed)
        picks = rnd.sample(MOMENTS, 24)
        picks.insert(12, "FREE: a very long look")
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
            fs = 9.2
            lines = wrap(p, "Garamond", fs, cell - 14)
            c.setFont("Garamond", fs); c.setFillColor(GREEN if free else INK)
            ty = y + cell / 2 + (len(lines) - 1) * 5.5 - 2
            for ln in lines:
                c.drawCentredString(x + cell / 2, ty, ln); ty -= 11
        self.done()

    def quotes_page(self):
        c, W = self.c, self.W
        self.frame("Lines to listen for", "Tick a line when you hear it, or something close. Screenwriters trim and reword.")
        x1, x2 = self.m + 24, W - self.m - 24
        h = (self.top - self.m - 40) / len(QUOTES)
        for i, (q, who) in enumerate(QUOTES):
            yy = self.top - 6 - i * h
            self.checkbox(x1, yy - 11, 9)
            c.setFont("GaramondIt", 10.6); c.setFillColor(INK)
            lines = wrap("“" + q + "”", "GaramondIt", 10.6, x2 - x1 - 34)
            for j, ln in enumerate(lines):
                c.drawString(x1 + 20, yy - 9 - j * 12.5, ln)
            c.setFont("Helvetica", 6.8); c.setFillColor(GOLD)
            c.drawString(x1 + 20, yy - 9 - len(lines) * 12.5 - 1, who.upper())
            self.line(x1, yy - h + 8, x2, RULE, 0.4)
        self.done()

    def book_vs_screen(self):
        c, W = self.c, self.W
        self.frame("The book against the screen", "Scene by scene. Tick a side, then write down why.")
        x1, x2 = self.m + 24, W - self.m - 24
        y = self.top - 10
        self.label("Scene", x1, y)
        for t, f in [("Book", 0.37), ("Screen", 0.45), ("Tie", 0.54), ("Why", 0.62)]:
            self.label(t, x1 + f * (x2 - x1), y)
        self.line(x1, y - 5, x2, GREEN, 0.9)
        step = (y - self.m - 36) / len(SCENES)
        for i, s in enumerate(SCENES, 1):
            yy = y - 5 - i * step
            self.line(x1, yy, x2)
            c.setFont("Garamond", 10.8); c.setFillColor(INK)
            for j, ln in enumerate(wrap(s, "Garamond", 10.8, 0.34 * (x2 - x1))):
                c.drawString(x1, yy + step / 2 + 2 - j * 12, ln)
            for f in (0.37, 0.45, 0.54):
                self.checkbox(x1 + f * (x2 - x1) + 3, yy + step / 2 - 5, 9)
            self.line(x1 + 0.62 * (x2 - x1), yy + 8, x2, RULE, 0.4)
        self.done()

    def vocabulary(self):
        c, W = self.c, self.W
        self.frame("A little Regency vocabulary", "Words that carry the plot.")
        x1, x2 = self.m + 24, W - self.m - 24
        y = self.top - 8
        step = 48
        for term, d in WORDS:
            self.smallcaps(term, x1, y - 10, 12.5, GREEN)
            c.setFont("Garamond", 10); c.setFillColor(INK)
            for j, ln in enumerate(wrap(d, "Garamond", 10, x2 - x1 - 105)):
                c.drawString(x1 + 100, y - 8 - j * 12, ln)
            self.line(x1, y - step + 14, x2, RULE, 0.4)
            y -= step
        self.label("Places", x1, y - 4)
        px = x1
        for i, (n, d) in enumerate(PLACES):
            col, row = divmod(i, 3)
            tx = x1 + col * ((x2 - x1) / 2)
            ty = y - 20 - row * 15
            c.setFont("Garamond", 10.5); c.setFillColor(GREEN); c.drawString(tx, ty, n)
            c.setFont("GaramondIt", 9.5); c.setFillColor(INK)
            c.drawString(tx + pdfmetrics.stringWidth(n, "Garamond", 10.5) + 6, ty, d)
        self.done()

    def party(self):
        c, W = self.c, self.W
        self.frame("Host a watch party", "A tea table, a pencil for everyone and a bingo card each.")
        x1, x2 = self.m + 24, W - self.m - 24
        y = self.top - 6
        for lab, w in [("Date", 120), ("Time", 90), ("Where", x2 - x1 - 240)]:
            pass
        self.label("Date", x1, y); self.line(x1 + 28, y - 2, x1 + 150)
        self.label("Time", x1 + 168, y); self.line(x1 + 196, y - 2, x1 + 290)
        self.label("Where", x1 + 308, y); self.line(x1 + 340, y - 2, x2)
        y -= 34
        half = (x2 - x1 - 20) / 2
        self.label("Guests and replies", x1, y)
        for i in range(8):
            yy = y - 6 - (i + 1) * 20
            self.line(x1, yy, x1 + half); self.checkbox(x1 + half - 12, yy + 4, 8)
        self.label("The tea table", x1 + half + 20, y)
        for i in range(8):
            yy = y - 6 - (i + 1) * 20
            self.line(x1 + half + 20, yy, x2)
        y = y - 6 - 8 * 20 - 26
        self.label("Before the guests arrive", x1, y)
        todo = ["Print a bingo card for each guest and find pencils", "Print the episode notes and the cast page",
                "Choose the music for the interval", "Set out the questions page", "Check the sound and the subtitles",
                "Put the kettle on at the interval, not before", "Decide who plays Mr Collins in the discussion"]
        for i, t in enumerate(todo):
            yy = y - 8 - (i + 1) * 17
            self.checkbox(x1, yy, 8); c.setFont("Garamond", 10.5); c.setFillColor(INK); c.drawString(x1 + 15, yy + 1, t)
        y = y - 8 - len(todo) * 17 - 34
        self.label("Music for the interval", x1, y)
        y = self.ruled(x1, y - 2, x2 - x1, 3, 19) - 22
        self.label("Who sits where, and who gets the good chair", x1, y)
        y = self.ruled(x1, y - 2, x2 - x1, 2, 19) - 22
        self.label("Next time", x1, y)
        self.ruled(x1, y - 2, x2 - x1, max(2, int((y - self.m - 36) / 19)), 19)
        self.done()

    def questions_page(self):
        c, W = self.c, self.W
        self.frame("Twelve questions for the sofa", "No right answers. Write yours before you hear anyone else's.")
        x1, x2 = self.m + 24, W - self.m - 24
        h = (self.top - self.m - 34) / len(QUESTIONS)
        for i, q in enumerate(QUESTIONS, 1):
            yy = self.top - 6 - (i - 1) * h
            c.setFont("Garamond", 17); c.setFillColor(GOLD); c.drawString(x1, yy - 14, f"{i}")
            c.setFont("Garamond", 10.8); c.setFillColor(INK)
            lines = wrap(q, "Garamond", 10.8, x2 - x1 - 30)
            for j, ln in enumerate(lines):
                c.drawString(x1 + 22, yy - 10 - j * 12.5, ln)
            self.line(x1 + 22, yy - h + 12, x2, RULE, 0.5)
        self.done()

    def verdict(self):
        c, W = self.c, self.W
        self.frame("My verdict", "For when the credits roll.")
        x1, x2 = self.m + 26, W - self.m - 26
        y = self.top - 6
        self.label("Overall", x1, y); self.stars(x1 + 52, y + 2, 5, 6.5)
        y -= 36
        cats = ["Casting", "Costumes", "Music", "Locations", "Faithful to the book", "Elizabeth", "Darcy", "The supporting cast"]
        for i, t in enumerate(cats):
            col, row = divmod(i, 4)
            tx = x1 + col * ((x2 - x1) / 2)
            ty = y - row * 26
            c.setFont("Garamond", 11); c.setFillColor(INK); c.drawString(tx, ty, t)
            self.stars(tx + 128, ty + 3, 5, 4.2)
        y -= 4 * 26 + 18
        self.label("Would I watch it again?", x1, y)
        for j, t in enumerate(["Yes", "Maybe", "No"]):
            tx = x1 + 150 + j * 62
            self.checkbox(tx, y - 1, 8); c.setFont("Garamond", 10.5); c.setFillColor(INK); c.drawString(tx + 13, y, t)
        y -= 34
        for lab, n in [("In one sentence", 2), ("The scene I will rewatch", 3), ("What I would change", 3), ("Who should read the book next", 2)]:
            self.label(lab, x1, y)
            y = self.ruled(x1, y - 4, x2 - x1, n, 20) - 22
        self.done()

    def first_line_card(self):
        c, W, H = self.c, self.W, self.H
        self.frame()
        c.setStrokeColor(GOLD); c.setLineWidth(2)
        bx, by, bw, bh = self.m + 40, H * 0.30, W - 2 * self.m - 80, H * 0.40
        c.roundRect(bx, by, bw, bh, 10)
        c.setLineWidth(0.6); c.roundRect(bx + 8, by + 8, bw - 16, bh - 16, 7)
        text = "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife."
        c.setFont("GaramondIt", 25); c.setFillColor(GREEN)
        lines = wrap(text, "GaramondIt", 25, bw - 70)
        ty = by + bh / 2 + (len(lines) - 1) * 16
        for ln in lines:
            c.drawCentredString(W / 2, ty, ln); ty -= 32
        c.setFont("Helvetica", 7.5); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, by + 28, "JANE AUSTEN  ·  PRIDE AND PREJUDICE  ·  1813")
        c.setFont("GaramondIt", 11); c.setFillColor(INK)
        c.drawCentredString(W / 2, by - 30, "Cut it out and frame it, pin it above the sofa or use it as a bookmark.")
        self.done()

    def notes(self):
        self.frame("Notes", "Anything that did not fit elsewhere.")
        x1, x2 = self.m + 26, self.W - self.m - 26
        self.ruled(x1, self.top - 6, x2 - x1, int((self.top - self.m - 40) / 20), 20)
        self.done()

    def build(self):
        self.cover(); self.how_to(); self.read_plan()
        self.episodes(True); self.episodes(False)
        self.whos_who()
        for k, seed in zip("ABCD", (5, 15, 25, 35)):
            self.moments_bingo(k, seed)
        self.quotes_page(); self.book_vs_screen(); self.vocabulary()
        self.party(); self.questions_page(); self.verdict(); self.first_line_card(); self.notes()
        self.c.save()


if __name__ == "__main__":
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    for name, size in (("letter", letter), ("a4", A4)):
        k = PP(out / f"pride-prejudice-watch-kit-{name}.pdf", size)
        k.build()
        print(name, k.page_no, "pages")
