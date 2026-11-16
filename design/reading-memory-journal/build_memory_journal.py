"""The Reader's Memory Journal: a printable keepsake diary of reading (not a tracker), US Letter and A4, EN and ES.

  python build_memory_journal.py FONTS_DIR OUT_DIR
FONTS_DIR needs EBGaramond.ttf and EBGaramond-Italic.ttf (SIL OFL 1.1). Writes four PDFs to OUT_DIR:
readers-memory-journal-{letter,a4}.pdf and diario-de-memorias-lectoras-{letter,a4}.pdf.
Same look as the Reading Challenge Kit (design/reading-challenge-kit/build_kit.py, whose Kit class is reused).
The buyers' PDFs are uploaded through /admin/digital and are not committed.
"""
import random
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfbase import pdfmetrics

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reading-challenge-kit"))
import build_kit as bk  # noqa: E402  (reads FONTS_DIR from sys.argv[1])
from build_kit import GOLD, GREEN, INK, SHELF  # noqa: E402

TX = {
    "en": {
        "doc_title": "The Reader's Memory Journal", "personal": "for personal use",
        "cover_the": "The", "cover_t1": "Reader's", "cover_t2": "Memory Journal",
        "cover_sub": "Not what you read. What it was like to read it.",
        "cover_foot": "BOOK MEMORIES  ·  QUOTES  ·  LETTERS  ·  A YEAR IN MEMORIES",
        "own_title": "This journal belongs to", "own_name": "Name", "own_since": "Started on",
        "gift_title": "Giving it as a gift?", "gift_to": "To", "gift_from": "From", "gift_note": "A note",
        "how_title": "How to use it", "how_sub": "There is no right order and nothing to finish.",
        "how": [
            ("Print what you need", "Print the whole journal, or only the pages you will use. Print more of the Book Memory page when you run out."),
            ("Write one memory per book", "Not a review. Where you were, who you were with, what the book felt like. Future you will want exactly that."),
            ("Keep a scrap", "A ticket, a pressed leaf, a receipt used as a bookmark. Tape it in the box on each Book Memory page."),
            ("Skip freely", "Leave any line empty. The letters and lists are for the days you feel like them."),
            ("Use it on a tablet", "Works in GoodNotes, Notability or any PDF app, so you can write with a stylus."),
        ],
        "life_title": "My reading life", "life_sub": "Five questions to begin with. Answer the ones that come easily.",
        "life": [("The first book I remember", 3), ("Who read to me, or taught me to read", 3),
                 ("The book that made me a reader", 3), ("The book I pretend I read", 2), ("What reading gives me now", 3)],
        "places_title": "Where I read", "places_sub": "The chair, the window, the train. Draw it, describe it, tape a photo.",
        "places": ["My favourite spot", "The place I read when nobody is looking", "The strangest place I have read"],
        "rituals": "My reading rituals: the drink, the light, the season, the soundtrack",
        "mem_title": "A Book to Remember", "mem_sub": "Where you were matters as much as what you read.",
        "mem_book": "Book", "mem_author": "Author", "mem_from": "Read from", "mem_to": "to",
        "mem_where": "Where I was", "mem_who": "Who I was with, or who gave it to me",
        "mem_life": "What was happening in my life", "mem_felt": "How it felt",
        "moods": ["cozy", "gripped", "wistful", "restless", "moved", "amused"],
        "mem_line": "The line I will keep", "mem_scrap": "A scrap to keep",
        "scrap_hint": "ticket · leaf · receipt · note",
        "quotes_title": "Lines I want to keep", "quotes_sub": "Copy them exactly. Note the page, so you can find them again.",
        "q_from": "from", "q_page": "page",
        "letter_title": "A Letter to a Character", "letter_sub": "Tell them what you would have said, or what you would have done.",
        "letter2_title": "A Letter to an Author", "letter2_sub": "You can say thank you to a writer who will never read it. Say it anyway.",
        "letter3_title": "A Letter to My Younger Self as a Reader",
        "letter3_sub": "Which book would you hand over, and what would you say to go with it?",
        "dear": "Dear", "yours": "Yours,",
        "gifts_title": "Books Given and Received", "gifts_sub": "A book that travels between two people takes both of them with it.",
        "g_cols": ["Book", "Given to / by", "Why"],
        "changed_title": "Books That Changed Me", "changed_sub": "Twelve at most. One line each on what changed.",
        "again_title": "Read Again, Leave Behind",
        "again_left": "Books I will read again", "again_right": "Books I stopped and do not regret",
        "again_sub": "Rereading is a kind of loyalty. Quitting is a kind of honesty.",
        "year_title": "My Year in Memories", "year_sub": "Fill it in on the last evening of the year, with something warm to drink.",
        "year": [("The moment I will remember most", 3), ("The book that surprised me", 2),
                 ("The one I am still thinking about", 2), ("A book that was in the right place at the right time", 2),
                 ("What I want to read next year, and where", 3)],
        "year_end": "One sentence for the reader I will be next year",
    },
    "es": {
        "doc_title": "El diario de memorias lectoras", "personal": "para uso personal",
        "cover_the": "El", "cover_t1": "Diario de", "cover_t2": "Memorias Lectoras",
        "cover_sub": "No lo que leíste. Cómo fue leerlo.",
        "cover_foot": "MEMORIAS DE LIBROS  ·  CITAS  ·  CARTAS  ·  UN AÑO DE MEMORIAS",
        "own_title": "Este diario pertenece a", "own_name": "Nombre", "own_since": "Empezado el",
        "gift_title": "¿Es un regalo?", "gift_to": "Para", "gift_from": "De", "gift_note": "Una nota",
        "how_title": "Cómo usarlo", "how_sub": "No hay un orden correcto ni nada que terminar.",
        "how": [
            ("Imprime lo que necesites", "Imprime todo el diario o solo las páginas que vayas a usar. Imprime más páginas de Memoria de un libro cuando se acaben."),
            ("Una memoria por libro", "No una reseña. Dónde estabas, con quién, cómo se sintió el libro. Tu yo del futuro querrá justo eso."),
            ("Guarda un recuerdo", "Una entrada, una hoja prensada, un recibo usado como marcapáginas. Pégalo en el recuadro de cada página."),
            ("Salta lo que quieras", "Deja cualquier línea vacía. Las cartas y las listas son para los días en que te apetezcan."),
            ("Úsalo en tablet", "Funciona en GoodNotes, Notability o cualquier app de PDF, para escribir con lápiz digital."),
        ],
        "life_title": "Mi vida como lector", "life_sub": "Cinco preguntas para empezar. Responde las que salgan fáciles.",
        "life": [("El primer libro que recuerdo", 3), ("Quién me leyó o me enseñó a leer", 3),
                 ("El libro que me hizo lector", 3), ("El libro que finjo haber leído", 2), ("Lo que me da leer ahora", 3)],
        "places_title": "Dónde leo", "places_sub": "El sillón, la ventana, el tren. Dibújalo, descríbelo, pega una foto.",
        "places": ["Mi rincón favorito", "Donde leo cuando nadie me mira", "El lugar más raro donde he leído"],
        "rituals": "Mis rituales de lectura: la bebida, la luz, la estación, la música",
        "mem_title": "Un libro para recordar", "mem_sub": "Dónde estabas importa tanto como lo que leíste.",
        "mem_book": "Libro", "mem_author": "Autor/a", "mem_from": "Lo leí desde", "mem_to": "hasta",
        "mem_where": "Dónde estaba", "mem_who": "Con quién estaba, o quién me lo regaló",
        "mem_life": "Qué pasaba en mi vida", "mem_felt": "Cómo se sintió",
        "moods": ["calma", "intriga", "nostalgia", "inquietud", "emoción", "risa"],
        "mem_line": "La frase que me quedo", "mem_scrap": "Un recuerdo para guardar",
        "scrap_hint": "entrada · hoja · recibo · nota",
        "quotes_title": "Frases que quiero guardar", "quotes_sub": "Cópialas tal cual. Anota la página para volver a encontrarlas.",
        "q_from": "de", "q_page": "página",
        "letter_title": "Carta a un personaje", "letter_sub": "Dile lo que le habrías dicho, o lo que habrías hecho.",
        "letter2_title": "Carta a un autor o autora", "letter2_sub": "Puedes dar las gracias a quien nunca te leerá. Dalas igual.",
        "letter3_title": "Carta a mi yo lector más joven",
        "letter3_sub": "¿Qué libro le entregarías y qué le dirías para acompañarlo?",
        "dear": "Querido/a", "yours": "Un abrazo,",
        "gifts_title": "Libros regalados y recibidos", "gifts_sub": "Un libro que viaja entre dos personas se lleva a las dos.",
        "g_cols": ["Libro", "Para / de quién", "Por qué"],
        "changed_title": "Libros que me cambiaron", "changed_sub": "Doce como máximo. Una línea sobre qué cambió.",
        "again_title": "Releer, dejar atrás",
        "again_left": "Libros que volveré a leer", "again_right": "Libros que dejé y no lamento",
        "again_sub": "Releer es una forma de lealtad. Abandonar, una de honestidad.",
        "year_title": "Mi año en memorias", "year_sub": "Complétalo la última tarde del año, con algo caliente para beber.",
        "year": [("El momento que más recordaré", 3), ("El libro que me sorprendió", 2),
                 ("El que sigo pensando", 2), ("Un libro que llegó en el momento justo", 2),
                 ("Qué quiero leer el año que viene, y dónde", 3)],
        "year_end": "Una frase para el lector que seré el año que viene",
    },
}


class Journal(bk.Kit):
    def __init__(self, path, size, tx):
        super().__init__(path, size)
        self.tx = tx
        self.c.setTitle(tx["doc_title"])
        self.step = 22 if size[1] < 800 else 24

    # --- furniture -------------------------------------------------------------------
    def frame(self, title=None, subtitle=None):
        super().frame(title, subtitle)
        c, W, m = self.c, self.W, self.m
        c.setFillColor(bk.PAPER); c.rect(m + 6, m + 5, W - 2 * m - 12, 16, stroke=0, fill=1)   # replace the kit's footer
        c.setFont("Helvetica", 6.5); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, m + 12, f"{self.tx['doc_title']}  ·  The Books Wanderer  ·  {self.tx['personal']}  ·  {self.page_no}")

    def wrap(self, text, font, size, width):
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if pdfmetrics.stringWidth(t, font, size) <= width:
                cur = t
            else:
                lines.append(cur); cur = w
        return lines + [cur] if cur else lines

    def inner(self):
        return self.m + 32, self.W - self.m - 32

    def field(self, label, x, y, w, n=1, step=None, italic_label=False):
        """Small label above n ruled lines. Returns the y below the last line."""
        step = step or self.step
        self.label(label, x, y)
        for i in range(n):
            self.line(x, y - 6 - (i + 1) * step + 6, x + w)
        return y - 14 - n * step + 6

    def lines_block(self, x, y, w, n, step=None):
        step = step or self.step
        for i in range(n):
            self.line(x, y - (i + 1) * step, x + w)
        return y - n * step

    def moods(self, x, y, words, w):
        c = self.c
        gap = w / len(words)
        for i, word in enumerate(words):
            cx = x + i * gap
            c.setStrokeColor(GOLD); c.setLineWidth(0.7); c.circle(cx + 5, y + 3, 4.6)
            c.setFont("GaramondIt", 10); c.setFillColor(INK); c.drawString(cx + 14, y, word)

    # --- pages -----------------------------------------------------------------------
    def cover(self):
        c, W, H, tx = self.c, self.W, self.H, self.tx
        self.frame()
        self.smallcaps(tx["cover_the"], W / 2, H * 0.66, 22, GOLD, center=True)
        self.smallcaps(tx["cover_t1"], W / 2, H * 0.60, 36, GREEN, center=True)
        self.smallcaps(tx["cover_t2"], W / 2, H * 0.54, 32, GREEN, center=True)
        c.setFont("GaramondIt", 14); c.setFillColor(INK)
        c.drawCentredString(W / 2, H * 0.48, tx["cover_sub"])
        # an open book with a few lines and a small sun: a memory, not a list
        cx, cy = W / 2, H * 0.34
        c.setStrokeColor(GOLD); c.setLineWidth(1); c.setFillColor(SHELF[0])
        for sgn in (-1, 1):
            p = c.beginPath(); p.moveTo(cx, cy - 34)
            p.curveTo(cx + sgn * 30, cy - 24, cx + sgn * 62, cy - 24, cx + sgn * 88, cy - 34)
            p.lineTo(cx + sgn * 88, cy + 26); p.curveTo(cx + sgn * 62, cy + 16, cx + sgn * 30, cy + 16, cx, cy + 26); p.close()
            c.drawPath(p, stroke=1, fill=1)
        c.setLineWidth(0.5)
        for k in range(5):
            for sgn in (-1, 1):
                c.line(cx + sgn * 14, cy + 8 - k * 9, cx + sgn * 76, cy + 12 - k * 9 - 4)
        c.setFillColor(SHELF[1]); c.circle(cx, cy + 64, 14, stroke=1, fill=1)
        c.setFont("Helvetica", 8); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, H * 0.20, tx["cover_foot"])
        c.setFont("Garamond", 11); c.setFillColor(GREEN)
        c.drawCentredString(W / 2, H * 0.155, "The Books Wanderer")
        self.done()

    def owner(self):
        c, W, tx = self.c, self.W, self.tx
        x0, x1 = self.inner()
        self.frame(tx["own_title"])
        y = self.top - 30
        y = self.field(tx["own_name"], x0, y, x1 - x0)
        y = self.field(tx["own_since"], x0, y - 6, (x1 - x0) / 2)
        y -= 28
        self.smallcaps(tx["gift_title"], W / 2, y, 16, GREEN, center=True)
        y -= 26
        y = self.field(tx["gift_to"], x0, y, x1 - x0)
        y = self.field(tx["gift_from"], x0, y - 6, x1 - x0)
        y = self.field(tx["gift_note"], x0, y - 6, x1 - x0, n=5)
        self.done()

    def how_to(self):
        c, W, tx = self.c, self.W, self.tx
        x0, x1 = self.inner()
        self.frame(tx["how_title"], tx["how_sub"])
        y = self.top - 24
        for i, (head, body) in enumerate(tx["how"], 1):
            c.setFont("Garamond", 24); c.setFillColor(GOLD); c.drawString(x0, y - 8, str(i))
            self.smallcaps(head, x0 + 34, y, 13, GREEN)
            c.setFont("Garamond", 11); c.setFillColor(INK)
            yy = y - 16
            for ln in self.wrap(body, "Garamond", 11, x1 - x0 - 34):
                c.drawString(x0 + 34, yy, ln); yy -= 14
            y -= 96
        self.done()

    def questions(self, title, sub, items, end_label=None):
        x0, x1 = self.inner()
        self.frame(title, sub)
        y = self.top - 16
        for label, n in items:
            y = self.field(label, x0, y, x1 - x0, n=n, step=self.step + 4) - 10
        if end_label:
            y = self.field(end_label, x0, y, x1 - x0, n=2, step=self.step + 4)
        self.done()

    def places(self):
        c, tx = self.c, self.tx
        x0, x1 = self.inner()
        self.frame(tx["places_title"], tx["places_sub"])
        y = self.top - 12
        bw = (x1 - x0 - 16) / 2
        bh = 150
        for i, label in enumerate(tx["places"][:2]):
            self.box(x0 + i * (bw + 16), y - bh, bw, bh, title=label)
        y -= bh + 16
        self.box(x0, y - bh, x1 - x0, bh, title=tx["places"][2])
        y -= bh + 22
        self.field(tx["rituals"], x0, y, x1 - x0, n=6, step=self.step)
        self.done()

    def memory(self):
        c, tx = self.c, self.tx
        x0, x1 = self.inner()
        iw = x1 - x0
        self.frame(tx["mem_title"], tx["mem_sub"])
        y = self.top - 10
        self.field(tx["mem_book"], x0, y, iw * 0.6, step=self.step - 4)
        self.field(tx["mem_author"], x0 + iw * 0.64, y, iw * 0.36, step=self.step - 4)
        y -= 34
        self.label(tx["mem_from"], x0, y); self.line(x0 + 56, y - 2, x0 + 150)
        self.label(tx["mem_to"], x0 + 160, y); self.line(x0 + 178, y - 2, x0 + 272)
        self.stars(x1 - 96, y + 1, s=4.6)
        y -= 26
        y = self.field(tx["mem_where"], x0, y, iw, n=2) - 4
        y = self.field(tx["mem_who"], x0, y, iw, n=2) - 4
        y = self.field(tx["mem_life"], x0, y, iw, n=3) - 6
        self.label(tx["mem_felt"], x0, y)
        self.moods(x0, y - 18, tx["moods"], iw)
        y -= 38
        lw = iw * 0.56
        self.label(tx["mem_line"], x0, y)
        bottom = self.m + 34
        n = max(3, int((y - 14 - bottom) // self.step))
        self.lines_block(x0, y - 6, lw, n)
        bx, bh = x0 + lw + 14, min(n * self.step, 150)
        self.box(bx, y - 10 - bh, x1 - bx, bh, title=tx["mem_scrap"])
        c.setFont("GaramondIt", 8); c.setFillColor(GOLD)
        c.drawCentredString((bx + x1) / 2, y - 10 - bh + 8, tx["scrap_hint"])
        self.done()

    def quotes(self, part):
        c, tx = self.c, self.tx
        x0, x1 = self.inner()
        self.frame(tx["quotes_title"], tx["quotes_sub"])
        y = self.top - 14
        slot = (y - self.m - 36) / 6
        for i in range(6):
            top = y - i * slot
            self.line(x0, top - 22, x1); self.line(x0, top - 22 - self.step + 2, x1)
            c.setFont("GaramondIt", 9); c.setFillColor(GOLD)
            c.drawString(x0, top - 22 - 2 * self.step + 8, tx["q_from"] + " ")
            self.line(x0 + 28, top - 22 - 2 * self.step + 6, x1 - 70)
            c.drawString(x1 - 64, top - 22 - 2 * self.step + 8, tx["q_page"] + " ")
            self.line(x1 - 34, top - 22 - 2 * self.step + 6, x1)
            c.setFont("Garamond", 22); c.setFillColor(GOLD); c.drawString(x0 - 13, top - 14, "“")
        self.done()

    def letter(self, title_key, sub_key, recipient=True):
        c, tx = self.c, self.tx
        x0, x1 = self.inner()
        self.frame(tx[title_key], tx[sub_key])
        y = self.top - 14
        c.setFont("GaramondIt", 12); c.setFillColor(INK)
        if recipient:
            c.drawString(x0, y, tx["dear"] + " "); self.line(x0 + pdfmetrics.stringWidth(tx["dear"] + " ", "GaramondIt", 12), y - 2, x0 + 240)
        y -= 10
        n = int((y - self.m - 70) // (self.step - 1))
        self.lines_block(x0, y, x1 - x0, n, step=self.step - 1)
        yy = y - n * (self.step - 1) - 22
        c.drawString(x1 - 150, yy, tx["yours"]); self.line(x1 - 110, yy - 2, x1)
        self.done()

    def gifts(self):
        c, tx = self.c, self.tx
        x0, x1 = self.inner()
        iw = x1 - x0
        self.frame(tx["gifts_title"], tx["gifts_sub"])
        y = self.top - 6
        cols = [x0, x0 + iw * 0.38, x0 + iw * 0.66, x1]
        for i, name in enumerate(tx["g_cols"]):
            self.label(name, cols[i] + 3, y)
        rows = int((y - self.m - 40) // (self.step + 2))
        for r in range(rows):
            yy = y - 12 - (r + 1) * (self.step + 2) + 12
            self.line(x0, yy, x1)
        # faint column dividers
        c.setStrokeColor(bk.RULE); c.setLineWidth(0.4)
        for xc in cols[1:3]:
            c.line(xc - 4, y - 8, xc - 4, y - 12 - rows * (self.step + 2) + 12)
        self.done()

    def changed(self):
        c, tx = self.c, self.tx
        x0, x1 = self.inner()
        self.frame(tx["changed_title"], tx["changed_sub"])
        y = self.top - 14
        slot = (y - self.m - 40) / 12
        for i in range(12):
            t = y - i * slot
            c.setFont("Garamond", 18); c.setFillColor(GOLD); c.drawString(x0, t - 14, f"{i + 1}")
            self.line(x0 + 24, t - 14, x1)
            self.line(x0 + 24, t - 14 - slot * 0.48, x1)
        self.done()

    def again(self):
        c, tx = self.c, self.tx
        x0, x1 = self.inner()
        self.frame(tx["again_title"], tx["again_sub"])
        y = self.top - 10
        cw = (x1 - x0 - 24) / 2
        n = int((y - self.m - 56) // (self.step + 2))
        for k, key in enumerate(("again_left", "again_right")):
            x = x0 + k * (cw + 24)
            self.label(tx[key], x, y)
            self.lines_block(x, y - 4, cw, n, step=self.step + 2)
        self.done()

    def year(self):
        tx = self.tx
        self.questions(tx["year_title"], tx["year_sub"], tx["year"], end_label=tx["year_end"])


def build(lang, size, out):
    j = Journal(out, size, TX[lang])
    j.cover(); j.owner(); j.how_to()
    j.questions(TX[lang]["life_title"], TX[lang]["life_sub"], TX[lang]["life"])
    j.places()
    for _ in range(18):
        j.memory()
    for part in (1, 2):
        j.quotes(part)
    j.letter("letter_title", "letter_sub"); j.letter("letter2_title", "letter2_sub"); j.letter("letter3_title", "letter3_sub", recipient=False)
    j.gifts(); j.changed(); j.again(); j.year()
    j.c.save()
    return j.page_no


if __name__ == "__main__":
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    names = {"en": "readers-memory-journal", "es": "diario-de-memorias-lectoras"}
    for lang in ("en", "es"):
        for label, size in (("letter", letter), ("a4", A4)):
            n = build(lang, size, out / f"{names[lang]}-{label}.pdf")
            print(lang, label, n, "pages")
