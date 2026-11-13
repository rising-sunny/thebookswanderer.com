"""The Book Club Kit: a printable PDF, US Letter and A4, for the store and Etsy.

  python build_kit.py <fonts_dir>   # writes out/book-club-kit-letter.pdf and -a4.pdf

Reuses the page furniture of the 2027 Reading Challenge Kit (design/reading-challenge-kit).
All questions, prompts and texts are original. The kit is independent of any book, film,
series, publisher or reading challenge brand.
"""
import importlib.util
import math
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

GREEN, GOLD, INK, RULE, SHELF = rck.GREEN, rck.GOLD, rck.INK, rck.RULE, rck.SHELF
TITLE = "The Book Club Kit"

# --- Question cards: 54 for any book, then 18 for each of four kinds of book -------------------
ANY_BOOK = [
    "What was the very first thing you thought when you finished the last page?",
    "Which sentence would you underline, and what does it do for the book?",
    "Where did you slow down, and where did you skim?",
    "Which character did you trust least at the start? Did that change?",
    "If this book were a place, what would it be like to live there?",
    "What did the author leave out that you wish had been in?",
    "Which scene would you keep if you could keep only one?",
    "Did the title mean something different by the end?",
    "Who is the book really about, and is it the person on the cover?",
    "What do you think happens the day after the last page?",
    "Which chapter could be cut without anyone noticing, and which one is the heart?",
    "Name a moment where you disagreed with a character out loud, or wanted to.",
    "What does this book believe about people? Do you agree?",
    "If you could ask the author one question, what would it be?",
    "How did the way the story is told (voice, order, point of view) change how you felt?",
    "Which minor character deserves their own book?",
    "What does the setting do that another place could not?",
    "Was there a moment you put the book down on purpose? Why?",
    "Which part felt most true to your own life?",
    "What would you say to someone who disliked this book?",
    "What would you say to someone who loved it?",
    "Which line of dialogue sounds like something a real person would say?",
    "What is the book afraid of?",
    "What did you know too early, or find out too late?",
    "Did the ending feel earned, rushed, or too tidy?",
    "Which decision in the book would you have made differently?",
    "What is the smallest detail you keep thinking about?",
    "Who would you give this book to, and who would you keep it from?",
    "How would a different decade have changed this story?",
    "What did the first page promise, and did the book keep that promise?",
    "Which feeling did the book make you feel most, and on which page?",
    "Is there a character you disliked and yet understood?",
    "What did you learn from this book that you did not expect to learn?",
    "How would you describe the book in three words?",
    "Which two characters should never have met? Which two should have met sooner?",
    "What is the book's biggest risk, and did it pay off?",
    "Which object matters most in the story, and why?",
    "What does the weather, the season or the time of day do in this book?",
    "If you were casting the characters as friends, who would you invite to dinner?",
    "What is the most surprising thing about how you felt while reading it?",
    "What would you cut from the cover blurb? What would you add?",
    "Which chapter would you read aloud to the group?",
    "How did this book change over the weeks, or the days, you spent reading it?",
    "What is the question the book keeps asking without saying it?",
    "Which character changes the most, and what changes them?",
    "What would you have wanted the author to do with the last chapter?",
    "Where did the book surprise you by being funny, tender or harder than expected?",
    "What do you want to remember from this book in a year?",
    "If this book had a soundtrack, what would the first song be?",
    "Which question about this book did nobody ask yet?",
    "Does the book change how you will read the next one?",
    "What is the most quotable thing in it, and what makes it quotable?",
    "If the club could change one thing about the book, what would it be?",
    "Would you read it again? When, and for what reason?",
]
PACKS = [
    ("Romance and romantasy", [
        "What keeps the two main characters apart, and is the reason strong enough?",
        "Which moment made you believe they belong together?",
        "How does the book handle trust: given, earned or broken?",
        "Which trope did the book use, and did it make it feel new?",
        "Who has more to lose, and how does the author show it?",
        "What does each character want apart from the other one?",
        "Was the pacing of the relationship satisfying, rushed or slow?",
        "Which supporting friendship or family tie carried the book for you?",
        "If the story has a magic system or a made-up world, what are its rules and its costs?",
        "How do the world's rules shape the love story?",
        "Which scene was a quiet moment that mattered more than a big one?",
        "Do the characters talk to each other honestly? When do they stop?",
        "What does the book say about being chosen, and about choosing?",
        "How did the setting help the romance, or get in its way?",
        "Which line would you save to send to someone?",
        "Did you want the ending the book gave you, or a different one?",
        "What would you ask one of the characters for advice about?",
        "What would a sequel have to do to keep the spell?",
    ]),
    ("Mystery and thriller", [
        "When did you first suspect the answer, and what tipped you off?",
        "Which clue looks different now that you know the ending?",
        "Which red herring fooled you the longest?",
        "Is the narrator honest with the reader? Where do you check?",
        "How does the author build tension: with action, with information, or with silence?",
        "Which character had the most believable reason, even if they were not guilty?",
        "Is the solution fair to the reader? Could you have solved it?",
        "What does the detective, or the main character, get wrong?",
        "What does the book think justice is, and do you agree?",
        "Which scene scared you, and what made it work?",
        "Where did the setting add to the mystery?",
        "Did the final reveal feel earned, or did it come from nowhere?",
        "Who suffers most from what happened, and does the book notice?",
        "Which question stays open after the last page?",
        "How would the story change if told by the culprit?",
        "What detail would you only notice on a second reading?",
        "Is the ending satisfying even if the case is solved?",
        "What would you change about the plot to make it harder to guess?",
    ]),
    ("Classics", [
        "Why do you think this book has lasted, and is it enough?",
        "What in it feels modern, and what feels foreign?",
        "Which sentence made you stop because of how it was written?",
        "How did the language slow you down, and what did you gain from that?",
        "Which character would be easiest to meet today, and which would be hardest?",
        "What assumptions of the time does the book carry? How does it handle them?",
        "What did the book get right about people that has not changed?",
        "Which part would you change if you were editing it today, and which would you leave alone?",
        "How does the book compare with what you expected before you opened it?",
        "Who is the book unfair to, and does it notice?",
        "Which scene do you think everyone remembers, and is it the right one?",
        "If it were published today, would it find readers?",
        "What does the ending tell us about what the author believed?",
        "How do money, class or family shape the plot?",
        "What would you like to know about the time it was written?",
        "Which edition did you read, and did the introduction or notes help?",
        "Who should read it first, and who should wait?",
        "What would you add to the shelf next to it?",
    ]),
    ("Nonfiction and memoir", [
        "What is the author's central claim, in your own words?",
        "Which part persuaded you most? Which part did not?",
        "What evidence did the author use, and was it enough?",
        "How does the author's own life or voice shape the argument?",
        "Which fact or story do you want to tell someone tonight?",
        "What did you already believe that the book challenged?",
        "What does the author leave out, on purpose or by accident?",
        "Whose voice is missing from this book?",
        "Would the book work as well if it were half as long?",
        "Which chapter changed how you saw something ordinary?",
        "How honest does the author seem to be about their own mistakes?",
        "What would you ask the people in the book?",
        "Which idea would you try in your own life, and which would you not?",
        "How does the structure (chronological, thematic, essays) help or hurt?",
        "What does the book say about memory, and how much do you trust it?",
        "What is the most useful sentence in the book?",
        "Who should read it, and what should they do afterwards?",
        "What do you still want to know?",
    ]),
]
ICEBREAKERS = [
    "Which book have you pretended to have read?",
    "Which fictional town would you move to tomorrow?",
    "What is the best last line you remember?",
    "Name a book you read in one sitting.",
    "Which cover made you buy a book?",
    "What is the longest you have taken to finish a book?",
    "Which character would you want as a neighbour?",
    "What is your reading spot, and what do you need there?",
    "Which book do you lend, and which do you never lend?",
    "What did you read as a child that you would still read now?",
    "Which genre do you avoid, and which one surprised you once?",
    "What is the book you most want everyone to have read?",
]
MOMENTS = [
    "Someone did not finish the book", "Someone read ahead and kept quiet", "A tangent about a TV series",
    "The host's pet joins in", "A page number is called out", "Someone changes their mind", "Everyone agrees (shocking)",
    "A character is called annoying", "Someone compares it to another book", "The ending divides the room",
    "A small spoiler slips out", "Snacks match the book", "A phone rings", "Someone reads a passage aloud",
    "Someone gives it five stars", "Someone gives it two stars", "The next book is argued about",
    "The date is moved", "Someone arrives late", "A quote is photographed", "Talk about the cover",
    "Someone says \"I cried\"", "Someone says \"I did not expect that\"", "Tea or wine is refilled",
    "Someone defends a character nobody likes", "Someone wants a sequel", "The book is lent to someone",
    "A chair is moved closer", "Someone brings notes", "A word is looked up", "Laughter at the wrong moment",
    "Someone asks \"Did anyone else get confused?\"", "A question stays open", "Someone is quoted back to themselves",
    "A new book is added to the list", "Someone says \"I will reread it\"",
]


def wrap(text, font, size, width):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(t, font, size) > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


class Club(rck.Kit):
    def __init__(self, path, size):
        super().__init__(path, size)
        self.c.setTitle(TITLE)

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
        c.drawCentredString(W / 2, m + 12, f"{TITLE}  ·  The Books Wanderer  ·  for personal use  ·  {self.page_no}")

    def checkbox(self, x, y, s=7):
        self.c.setStrokeColor(INK); self.c.setLineWidth(0.6); self.c.rect(x, y, s, s)

    def para(self, text, x, y, width, size=10.5, leading=14, font="Garamond", color=INK):
        self.c.setFont(font, size); self.c.setFillColor(color)
        for ln in wrap(text, font, size, width):
            self.c.drawString(x, y, ln); y -= leading
        return y

    def field(self, label, x, y, w):
        self.label(label, x, y + 4)
        self.line(x, y, x + w)

    # --- pages --------------------------------------------------------------------------------
    def cover(self):
        c, W, H = self.c, self.W, self.H
        self.frame()
        # a round table with chairs
        cx, cy, r = W / 2, H * 0.66, 48
        c.setFillColor(HexColor("#f4ecda")); c.setStrokeColor(GOLD); c.setLineWidth(1)
        c.circle(cx, cy, r, stroke=1, fill=1)
        c.setLineWidth(0.5); c.circle(cx, cy, r - 7, stroke=1, fill=0)
        for k in range(8):
            a = k * math.pi / 4 + math.pi / 8
            c.setFillColor(SHELF[k % len(SHELF)]); c.setStrokeColor(GOLD); c.setLineWidth(0.7)
            c.circle(cx + (r + 16) * math.cos(a), cy + (r + 16) * math.sin(a), 11, stroke=1, fill=1)
        for k, (dx, dy, col) in enumerate([(-14, 6, SHELF[1]), (2, -6, SHELF[0]), (14, 8, SHELF[2])]):
            c.setFillColor(col); c.setStrokeColor(GOLD); c.setLineWidth(0.6); c.rect(cx + dx - 9, cy + dy - 6, 18, 12, stroke=1, fill=1)
        self.smallcaps("The", W / 2, H * 0.50, 22, GOLD, center=True)
        self.smallcaps("Book Club", W / 2, H * 0.44, 36, GREEN, center=True)
        self.smallcaps("Kit", W / 2, H * 0.385, 30, GREEN, center=True)
        c.setFont("GaramondIt", 14); c.setFillColor(INK)
        c.drawCentredString(W / 2, H * 0.335, "Plan the year, choose the book, start the conversation.")
        c.setFont("Helvetica", 8); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, H * 0.265, "PLANNER  ·  VOTING  ·  126 QUESTION CARDS  ·  BINGO  ·  INVITATIONS  ·  YEAR IN REVIEW")
        c.setFont("Garamond", 11); c.setFillColor(GREEN)
        c.drawCentredString(W / 2, H * 0.215, "The Books Wanderer")
        self.done()

    def how_to(self):
        c, W = self.c, self.W
        self.frame("How to use this kit", "Print what you need, as many times as you need it.")
        steps = [
            ("Start with the charter", "Fill in the club page and the roster once. It takes ten minutes and saves a year of questions."),
            ("Plan the year", "The planner shows twelve gatherings on one page: book, host, date and what is on the table."),
            ("Choose the book together", "Everyone nominates, everyone ranks three. The tally sheet picks the winner without an argument."),
            ("Run the evening", "The agenda fits ninety minutes. The host checklist covers before, during and after."),
            ("Pick your cards", "Cut out five or six question cards for the night. The deck has questions for any book, and a deck each for romance and fantasy, mystery, classics and nonfiction."),
            ("Warm up and play", "Icebreaker cards for the first ten minutes, and four bingo cards for the moments every club knows."),
            ("Write it down", "A notes page for each gathering and a scoring sheet for the verdict."),
            ("Look back", "At the end of the year, the review pages turn twelve books into a favourite."),
        ]
        y, x = self.top - 20, self.m + 40
        for i, (head, body) in enumerate(steps, 1):
            c.setFont("Garamond", 22); c.setFillColor(GOLD); c.drawString(x, y - 6, f"{i}")
            self.smallcaps(head, x + 30, y, 13, GREEN)
            self.para(body, x + 30, y - 15, W - 2 * self.m - 90, 10.5, 13)
            y -= 58
        c.setFont("GaramondIt", 10); c.setFillColor(INK)
        c.drawCentredString(W / 2, self.m + 40, "Prints well on plain paper. Also works in GoodNotes, Notability or any PDF app on a tablet.")
        self.done()

    def charter(self):
        c, W = self.c, self.W
        self.frame("Our book club", "One page to say who we are and how we work.")
        x1, x2 = self.m + 30, W - self.m - 30
        y = self.top - 14
        self.field("Club name", x1, y, x2 - x1); y -= 34
        half = (x2 - x1 - 20) / 2
        self.field("Started", x1, y, half); self.field("We meet", x1 + half + 20, y, half); y -= 34
        self.field("Where", x1, y, half); self.field("Members (up to)", x1 + half + 20, y, half); y -= 38
        self.label("How we choose the book", x1, y); y -= 14
        for i, t in enumerate(["We vote (nominate, then rank three)", "The host chooses, in turn", "A theme each month, then a vote",
                               "We take turns by genre", "Anyone can suggest, the group decides"]):
            self.checkbox(x1, y - 1, 8); c.setFont("Garamond", 10.5); c.setFillColor(INK); c.drawString(x1 + 14, y, t); y -= 16
        y -= 12
        self.label("Our rules (keep them short)", x1, y)
        y = self.ruled(x1, y - 2, x2 - x1, 7, 22) - 14
        self.label("What we promise each other", x1, y); y -= 14
        for t in ["Be kind about the book, even when we disagree", "Say when we did not finish, without guilt",
                  "Keep spoilers out of the invitation", "Let everyone speak before anyone speaks twice"]:
            self.checkbox(x1, y - 1, 8); c.setFont("Garamond", 10.5); c.setFillColor(INK); c.drawString(x1 + 14, y, t); y -= 16
        y -= 14
        self.label("Our first meeting is on", x1, y); self.line(x1 + 100, y - 2, x1 + 100 + 150)
        self.done()

    def roster(self):
        W = self.W
        self.frame("The members", "Names, how to reach them, and the snack they are known for.")
        x1, x2 = self.m + 26, W - self.m - 26
        cols = [("Name", 0.0), ("Contact", 0.27), ("Favourite kind of book", 0.55), ("Birthday month", 0.78)]
        y = self.top - 10
        for lab, f in cols:
            self.label(lab, x1 + f * (x2 - x1), y)
        n = 14
        step = (y - self.m - 40) / n
        for i in range(n):
            yy = y - (i + 1) * step + 6
            self.line(x1, yy, x2)
            self.c.setFont("Helvetica", 6.5); self.c.setFillColor(GOLD); self.c.drawRightString(x1 - 4, yy + 2, f"{i + 1}")
        self.done()

    def planner(self):
        W = self.W
        self.frame("The year at a glance", "Twelve gatherings, one page.")
        x1, x2 = self.m + 26, W - self.m - 26
        cols = [("Month", 0.0, 0.14), ("Book and author", 0.14, 0.50), ("Host", 0.50, 0.64), ("Date", 0.64, 0.76), ("On the table", 0.76, 1.0)]
        y = self.top - 10
        for lab, a, _ in cols:
            self.label(lab, x1 + a * (x2 - x1) + 2, y)
        step = (y - self.m - 36) / 12
        for i, m in enumerate(rck.MONTHS):
            yy = y - (i + 1) * step + 6
            self.line(x1, yy, x2)
            self.c.setFont("Garamond", 11.5); self.c.setFillColor(GREEN); self.c.drawString(x1 + 2, yy + 8, m)
        for _, a, _ in cols[1:]:
            self.c.setStrokeColor(RULE); self.c.setLineWidth(0.4)
            xx = x1 + a * (x2 - x1)
            self.c.line(xx, y - 6, xx, y - 12 * step + 6)
        self.done()

    def nominations(self):
        W = self.W
        self.frame("Nominations", "Each member proposes up to two books. Say why in one line.")
        x1, x2 = self.m + 26, W - self.m - 26
        cols = [("Title", 0.0), ("Author", 0.34), ("Pages", 0.58), ("Kind of book", 0.67), ("Nominated by", 0.84)]
        y = self.top - 10
        for lab, f in cols:
            self.label(lab, x1 + f * (x2 - x1) + 2, y)
        n = 12
        step = (y - self.m - 150) / n
        for i in range(n):
            yy = y - (i + 1) * step + 6
            self.line(x1, yy, x2)
            self.c.setFont("Helvetica", 6.5); self.c.setFillColor(GOLD); self.c.drawRightString(x1 - 4, yy + 2, f"{i + 1}")
        yy = y - n * step - 18
        self.label("Why this one, in a sentence (for the books the group might not know)", x1, yy)
        self.ruled(x1, yy - 2, x2 - x1, 4, 20)
        self.done()

    def ballots(self):
        c, W, H = self.c, self.W, self.H
        self.frame("The ballot", "Rank your top three. First choice 3 points, second 2, third 1. Cut along the dotted lines.")
        x1, x2 = self.m + 30, W - self.m - 30
        h = (self.top - self.m - 40) / 3
        for k in range(3):
            y0 = self.top - 6 - k * h
            c.setStrokeColor(GOLD); c.setLineWidth(0.7); c.roundRect(x1, y0 - h + 12, x2 - x1, h - 18, 8)
            self.smallcaps("Our next book", x1 + 14, y0 - 22, 14, GREEN)
            c.setFont("Helvetica", 7); c.setFillColor(GOLD); c.drawRightString(x2 - 14, y0 - 20, "NAME  ____________________")
            c.setFont("Helvetica-Bold", 6.5); c.setFillColor(GOLD)
            for j, lab in enumerate(("1ST", "2ND", "3RD")):
                c.drawCentredString(x2 - 92 + j * 28, y0 - 44, lab)
            for i in range(5):
                yy = y0 - 62 - i * ((h - 100) / 4)
                self.checkbox(x1 + 16, yy - 2, 10)
                self.line(x1 + 34, yy - 2, x2 - 118)
                for j in range(3):
                    c.setStrokeColor(INK); c.setLineWidth(0.6); c.circle(x2 - 92 + j * 28, yy + 2.5, 4.5, stroke=1, fill=0)
            if k < 2:
                c.setStrokeColor(RULE); c.setDash(2, 3); c.line(self.m + 10, y0 - h + 6, W - self.m - 10, y0 - h + 6); c.setDash()
        self.done()

    def tally(self):
        W = self.W
        self.frame("The tally", "Write each ballot's points in a column. The highest total is the next book.")
        x1, x2 = self.m + 26, W - self.m - 26
        y = self.top - 10
        name_w = 0.34 * (x2 - x1)
        cells = 10
        cw = (x2 - x1 - name_w - 46) / cells
        self.label("Book", x1 + 2, y)
        for j in range(cells):
            self.label(f"#{j + 1}", x1 + name_w + j * cw + 4, y)
        self.label("Total", x2 - 40, y)
        n = 10
        step = (y - self.m - 120) / n
        for i in range(n):
            yy = y - (i + 1) * step + 6
            self.line(x1, yy, x2)
        for j in range(cells + 1):
            xx = x1 + name_w + j * cw
            self.c.setStrokeColor(RULE); self.c.setLineWidth(0.4); self.c.line(xx, y - 6, xx, y - n * step + 6)
        yy = y - n * step - 20
        self.c.setFont("GaramondIt", 11); self.c.setFillColor(INK)
        self.c.drawString(x1, yy, "If two books tie, the host picks the one the group has waited longest to read.")
        yy -= 30
        self.field("The winner is", x1, yy, (x2 - x1) * 0.7)
        self.done()

    def agenda(self):
        c, W = self.c, self.W
        self.frame("An evening in ninety minutes", "A shape to follow, and to bend.")
        x1, x2 = self.m + 36, W - self.m - 36
        steps = [
            ("0:00", "Arrive and settle", "Drinks, seats, phones away. No book talk yet."),
            ("0:10", "One sentence each", "Everyone says how the book left them, in one sentence. No replies yet."),
            ("0:20", "Warm-up card", "Draw one icebreaker card and go round the room."),
            ("0:30", "The big questions", "Draw three question cards. Let the answers wander."),
            ("0:55", "The hard question", "The one that divides the room. Ask for the other side before the first one repeats."),
            ("1:10", "Verdict and quotes", "Stars on the scoring sheet. Each member shares a line worth keeping."),
            ("1:20", "Choose the next book", "Nominations, ballots, tally. Or announce the host's pick."),
            ("1:25", "Close", "Date, place, who hosts. Thank the host. Write the notes."),
        ]
        y = self.top - 14
        row = (y - self.m - 40) / len(steps)
        for t, head, body in steps:
            c.setFont("Garamond", 20); c.setFillColor(GOLD); c.drawString(x1, y - 8, t)
            self.smallcaps(head, x1 + 70, y - 2, 13, GREEN)
            self.para(body, x1 + 70, y - 17, x2 - x1 - 70, 10.5, 13)
            self.line(x1, y - row + 14, x2, RULE, 0.4)
            y -= row
        self.done()

    def host_list(self):
        c, W = self.c, self.W
        self.frame("The host's checklist", "Before, during and after. Nothing to remember on the day.")
        x1 = self.m + 36
        blocks = [
            ("Two weeks before", ["Confirm the date, the time and the place", "Send the invitation, with the book and the date",
                                  "Check who has the book, and who needs a loan"]),
            ("The week before", ["Send a short reminder", "Choose five question cards and one icebreaker",
                                 "Decide on the drinks and the table", "Prepare a place to put the notes"]),
            ("On the day", ["Seats in a circle, with room for everyone to see everyone", "Cards, pens, the scoring sheet",
                            "Let the first person speak before you do", "Keep time lightly, and keep the next date for last"]),
            ("Afterwards", ["Write the notes page while it is fresh", "Send the next date and the next book",
                            "Thank the group, and anyone who brought something"]),
        ]
        y = self.top - 14
        for head, items in blocks:
            self.smallcaps(head, x1, y, 13, GREEN); y -= 18
            for t in items:
                self.checkbox(x1, y - 1, 8); c.setFont("Garamond", 10.5); c.setFillColor(INK); c.drawString(x1 + 14, y, t); y -= 16
            y -= 14
        x2 = self.W - self.m - 36
        self.label("Notes for this gathering", x1, y)
        self.ruled(x1, y - 2, x2 - x1, max(2, int((y - self.m - 44) / 20)), 20)
        self.done()

    def cards(self, title, subtitle, texts, tag, rows=6, start=0):
        """Cut-out cards: three across and six down (18) by default, four down (12) for the icebreakers."""
        c, W, H = self.c, self.W, self.H
        self.frame(title, subtitle)
        x1, x2 = self.m + 18, W - self.m - 18
        cols = 3
        cw = (x2 - x1) / cols
        ch = (self.top - self.m - 28) / rows
        for i, t in enumerate(texts):
            r, k = divmod(i, cols)
            x = x1 + k * cw
            y = self.top - 6 - r * ch
            c.setStrokeColor(RULE); c.setLineWidth(0.5); c.setDash(2, 3); c.rect(x, y - ch, cw, ch); c.setDash()
            c.setFont("Helvetica", 5.8); c.setFillColor(GOLD)
            c.drawString(x + 8, y - 11, f"{tag.upper()}  ·  {start + i + 1:02d}")
            self.stars(x + cw - 42, y - 11, 3, 2.2)
            size = 10.4 if rows == 4 else 9.6
            lines = wrap(t, "Garamond", size, cw - 22)
            if len(lines) > 6:
                size = 8.8
                lines = wrap(t, "Garamond", size, cw - 22)
            c.setFont("Garamond", size); c.setFillColor(INK)
            ty = y - 26
            for ln in lines:
                c.drawString(x + 11, ty, ln); ty -= size + 3.2
        self.done()

    def verdict(self):
        c, W = self.c, self.W
        self.frame("Our verdict", "Stars and a few words from every member. Copy it for each gathering.")
        x1, x2 = self.m + 26, W - self.m - 26
        y = self.top - 10
        self.field("The book", x1, y, (x2 - x1) * 0.55); self.field("Date", x1 + (x2 - x1) * 0.6, y, (x2 - x1) * 0.4); y -= 34
        self.label("Name", x1 + 2, y); self.label("Stars", x1 + (x2 - x1) * 0.28, y); self.label("In a few words", x1 + (x2 - x1) * 0.52, y)
        n = 12
        step = (y - self.m - 120) / n
        for i in range(n):
            yy = y - (i + 1) * step + 6
            self.line(x1, yy, x2)
            self.stars(x1 + (x2 - x1) * 0.28 + 4, yy + 4, 5, 3.6)
        yy = y - n * step - 20
        self.label("The average, and the line we will remember", x1, yy)
        self.ruled(x1, yy - 2, x2 - x1, 3, 20)
        self.done()

    def bingo(self, name, seed):
        c, W, H = self.c, self.W, self.H
        self.frame(f"Book club bingo {name}", "Mark a square when it happens. A line wins a round of tea; a full card wins the next pick.")
        x1, x2 = self.m + 40, W - self.m - 40
        size = (x2 - x1) / 5
        y0 = self.top - 40
        rnd = random.Random(seed)
        pool = MOMENTS[:]
        rnd.shuffle(pool)
        picks = pool[:24]
        k = 0
        for r in range(5):
            for col in range(5):
                x, y = x1 + col * size, y0 - (r + 1) * size
                c.setStrokeColor(GOLD); c.setLineWidth(0.7); c.rect(x, y, size, size)
                if r == 2 and col == 2:
                    c.setFont("Garamond", 15); c.setFillColor(GREEN)
                    c.drawCentredString(x + size / 2, y + size / 2 + 2, "The book")
                    c.setFont("GaramondIt", 9.5); c.setFillColor(GOLD)
                    c.drawCentredString(x + size / 2, y + size / 2 - 12, "was discussed")
                    continue
                lines = wrap(picks[k], "Garamond", 9.4, size - 12)
                ty = y + size / 2 + (len(lines) - 1) * 5.6 - 2
                c.setFont("Garamond", 9.4); c.setFillColor(INK)
                for ln in lines:
                    c.drawCentredString(x + size / 2, ty, ln); ty -= 11.2
                k += 1
        yy = y0 - 5 * size - 40
        half = (x2 - x1 - 20) / 2
        self.field("First line won by", x1, yy, half); self.field("Full card won by", x1 + half + 20, yy, half)
        yy -= 34
        self.field("The book we played during", x1, yy, x2 - x1)
        self.done()

    def icebreakers(self):
        self.cards("Icebreakers", "Twelve cards for the first ten minutes. Cut along the dotted lines.", ICEBREAKERS, "Icebreaker", rows=4)

    def invitations(self):
        c, W, H = self.c, self.W, self.H
        self.frame("Invitations", "Cut, fill in and send. Photograph it for the group chat if you prefer.")
        x1, x2 = self.m + 20, W - self.m - 20
        cols, rows = 2, 3
        cw = (x2 - x1) / cols
        ch = (self.top - self.m - 28) / rows
        for i in range(cols * rows):
            r, k = divmod(i, cols)
            x = x1 + k * cw
            y = self.top - 6 - r * ch
            c.setStrokeColor(RULE); c.setLineWidth(0.5); c.setDash(2, 3); c.rect(x, y - ch, cw, ch); c.setDash()
            c.setStrokeColor(GOLD); c.setLineWidth(0.8); c.roundRect(x + 8, y - ch + 8, cw - 16, ch - 16, 6)
            self.smallcaps("You are invited", x + cw / 2, y - 30, 14, GREEN, center=True)
            c.setFont("GaramondIt", 9.5); c.setFillColor(INK)
            c.drawCentredString(x + cw / 2, y - 44, "to talk about a book over something good to drink")
            fy = y - 68
            for lab in ["The book", "Date and time", "Where", "Host", "Bring (optional)"]:
                self.label(lab, x + 22, fy + 4, GOLD, 6)
                self.line(x + 22 + 66, fy, x + cw - 22)
                fy -= (ch - 96) / 5
        self.done()

    def notes(self, n):
        c, W = self.c, self.W
        self.frame(f"Gathering notes {n}", "What we said, what we decided, what we will remember.")
        x1, x2 = self.m + 26, W - self.m - 26
        y = self.top - 10
        half = (x2 - x1 - 20) / 2
        self.field("The book", x1, y, half); self.field("Date", x1 + half + 20, y, half); y -= 32
        self.field("Who came", x1, y, x2 - x1); y -= 32
        for lab, rows in [("What we said", 7), ("A line worth keeping, and who found it", 2), ("What we could not agree on", 3), ("Next time", 3)]:
            self.label(lab, x1, y)
            y = self.ruled(x1, y - 2, x2 - x1, rows, 20) - 18
        self.done()

    def year_one(self):
        W = self.W
        self.frame("The year in review", "Twelve books, in numbers.")
        x1, x2 = self.m + 26, W - self.m - 26
        bw, bh = (x2 - x1 - 16) / 3, 52
        y = self.top - 10
        stats = ["Books we read", "Meetings held", "Members who came", "Books we loved", "Books we argued about", "Books nobody finished",
                 "Longest book", "Shortest book", "Best snack"]
        for i, t in enumerate(stats):
            r, k = divmod(i, 3)
            self.box(x1 + k * (bw + 8), y - (r + 1) * (bh + 8), bw, bh, title=t)
        y -= 3 * (bh + 8) + 20
        self.label("The three that stayed with us", x1, y)
        for i in range(3):
            yy = y - 6 - (i + 1) * 26
            self.c.setFont("Garamond", 13); self.c.setFillColor(GOLD); self.c.drawString(x1, yy + 3, f"{i + 1}")
            self.line(x1 + 16, yy, x2)
        y = y - 6 - 3 * 26 - 24
        self.label("The book we would hand to another club, and why", x1, y)
        self.ruled(x1, y - 4, x2 - x1, max(2, int((y - self.m - 40) / 20)), 20)
        self.done()

    def year_two(self):
        W = self.W
        self.frame("Awards and next year", "Because every club deserves a ceremony.")
        x1, x2 = self.m + 26, W - self.m - 26
        y = self.top - 10
        for lab in ["Best discussion", "Funniest moment", "Biggest surprise", "Best host", "Best ending we read"]:
            self.field(lab, x1, y, x2 - x1); y -= 34
        y -= 8
        self.label("What we want more of next year", x1, y)
        y = self.ruled(x1, y - 2, x2 - x1, 3, 20) - 16
        self.label("What we would change", x1, y)
        y = self.ruled(x1, y - 2, x2 - x1, 3, 20) - 16
        self.label("The books we want to read together", x1, y)
        self.ruled(x1, y - 2, x2 - x1, max(2, int((y - self.m - 40) / 20)), 20)
        self.done()

    def end_page(self):
        c, W, H = self.c, self.W, self.H
        self.frame()
        self.smallcaps("Good books are better", W / 2, H * 0.58, 26, GREEN, center=True)
        self.smallcaps("with company", W / 2, H * 0.53, 26, GREEN, center=True)
        c.setFont("GaramondIt", 13); c.setFillColor(INK)
        c.drawCentredString(W / 2, H * 0.46, "Thank you for using the kit. Print it again whenever the club does.")
        c.setFont("Helvetica", 8); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, H * 0.38, "THE BOOKS WANDERER  ·  THEBOOKSWANDERER.COM")
        c.setFont("GaramondIt", 9.5); c.setFillColor(INK)
        c.drawCentredString(W / 2, H * 0.32, "For personal and club use. Not for resale or redistribution.")
        self.done()

    def build(self):
        self.cover(); self.how_to(); self.charter(); self.roster(); self.planner()
        self.nominations(); self.ballots(); self.tally(); self.agenda(); self.host_list()
        for i in range(3):
            self.cards("Questions for any book", f"Cut along the dotted lines. Page {i + 1} of 3.", ANY_BOOK[i * 18:(i + 1) * 18], "Any book", start=i * 18)
        for name, qs in PACKS:
            self.cards(name, "Questions for this kind of book. Cut along the dotted lines.", qs, name.split(" ")[0])
        self.verdict(); self.bingo("A", 11); self.bingo("B", 22); self.bingo("C", 33); self.bingo("D", 44)
        self.icebreakers(); self.invitations()
        for n in (1, 2, 3):
            self.notes(n)
        self.year_one(); self.year_two(); self.end_page()
        self.c.save()


if __name__ == "__main__":
    assert len(ANY_BOOK) == 54 and all(len(q) == 18 for _, q in PACKS) and len(ICEBREAKERS) == 12
    assert len(set(ANY_BOOK)) == 54 and len(MOMENTS) >= 24
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    for name, size in (("letter", letter), ("a4", A4)):
        k = Club(out / f"book-club-kit-{name}.pdf", size)
        k.build()
        print(name, k.page_no, "pages")
