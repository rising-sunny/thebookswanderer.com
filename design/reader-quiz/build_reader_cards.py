"""Free "reader card" printables for the reader-type quiz: one two-page PDF per type (cozy, annotator, wanderer),
English and Spanish, US Letter. The other two types reuse existing free gifts (challenger: the 52-book challenge,
classic: the Jane Austen plan).

  python build_reader_cards.py FONTS_DIR OUT_DIR       # FONTS_DIR needs EBGaramond.ttf and EBGaramond-Italic.ttf
Writes reader-card-{cozy,annotator,wanderer}.pdf and tarjeta-lector-{acogedor,anotador,viajero}.pdf to OUT_DIR
(normally assets/downloads/). Same look as the Reading Challenge Kit (design/reading-challenge-kit/build_kit.py).
"""
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reading-challenge-kit"))
import build_kit as bk  # noqa: E402  (reads FONTS_DIR from sys.argv[1])
from build_kit import GOLD, GREEN, INK  # noqa: E402

T = {
    "en": {
        "label": "YOUR READER CARD", "foot": "The Books Wanderer  ·  for personal use", "rituals": "Your three small rituals",
        "cut": "Cut out your bookmarks", "cut_hint": "Print at 100%, cut along the dotted lines, fold in half or use as they are.",
        "cozy": {
            "name": "The Cozy Nester", "tag": "Reading is where you go to feel at home.",
            "body": "You reread the books that feel like a blanket, you notice the light in a room before the furniture, and you are happiest when the world is a little quieter than usual. You do not read to get through a list. You read to be somewhere kind.",
            "rit": ["Make the spot before the book: a blanket, a lamp, something warm to drink.",
                    "Keep one comfort reread within arm's reach for the days that need it.",
                    "Finish with ten quiet minutes. No phone, no next book yet."],
            "marks": ["Just one more chapter.", "Tea first. Then the book.", "Do not disturb: reading."],
            "p2": "My reading nook", "p2sub": "What makes a corner yours. Tick what you have, circle what you want.",
            "check": ["A blanket within reach", "A lamp with warm light", "A drink that stays warm", "A cushion for the elbow",
                      "A bookmark that does not fall out", "A place for the book when I fall asleep", "A window or a rain sound",
                      "A shelf within sight", "A comfort reread nearby", "A reason to stay"],
            "lists": [("Comfort rereads I love", 5), ("Books for this winter", 5), ("For my nook, one day", 3)],
        },
        "annotator": {
            "name": "The Annotator", "tag": "A book is not finished until you have argued with it.",
            "body": "You read with a pencil, you cannot lend a book without a pang, and you trust a margin more than a review. For you a page is a place to think, and a book gets better with every line you leave in it.",
            "rit": ["Choose a pen you like and keep it inside the book you are reading.",
                    "Copy one line a week into a notebook, with the page number.",
                    "Reread your own notes before you start the next book."],
            "marks": ["Underline the line you will want again.", "Write back: ask the book a question.", "Leave a mark. It was here, and so were you."],
            "p2": "My annotation key", "p2sub": "Six symbols are enough. Use them for a month and they become a habit.",
            "check": None,
            "key": [("a line under the text", "A line worth keeping"), ("?", "A question for the book, or for me"), ("!", "A surprise, a turn, a laugh"),
                    ("*", "A favourite: come back to this one"), ("→", "This connects to another page or book"), ("✓", "I agree; this is true for me")],
            "asks": ["What did I expect here, and what happened instead?", "Which sentence would I read aloud?", "Who would I send this page to?"],
            "lists": [("Lines I copied this month", 6)],
        },
        "wanderer": {
            "name": "The Wanderer", "tag": "Every book is a ticket to somewhere.",
            "body": "You choose a book because of where it is set, you look up the map after a good chapter, and a translated novel feels like a small border crossing. Reading is how you travel when you cannot, and how you remember where you have been.",
            "rit": ["Find the place on a map before you start, even a place that does not exist.",
                    "Read one translated book a season. Notice what the translator chose.",
                    "Note where you read each book as well as where it is set."],
            "marks": ["BOARDING PASS · Page ___ to page ___", "Destination: the last chapter.", "Seat: this chair. Departure: now."],
            "p2": "Around the world in 12 books", "p2sub": "One country, one book, one month. Choose them at your own pace.",
            "check": None, "world": ("Country or place", "Book", "Author"),
            "lists": [],
        },
    },
    "es": {
        "label": "TU TARJETA DE LECTOR", "foot": "The Books Wanderer  ·  para uso personal", "rituals": "Tus tres pequeños rituales",
        "cut": "Recorta tus marcapáginas", "cut_hint": "Imprime al 100 %, recorta por las líneas de puntos, dobla por la mitad o úsalos tal cual.",
        "cozy": {
            "name": "El lector acogedor", "tag": "Leer es donde vas para sentirte en casa.",
            "body": "Relees los libros que se sienten como una manta, te fijas en la luz de una habitación antes que en los muebles y eres más feliz cuando el mundo está un poco más callado de lo normal. No lees para terminar una lista. Lees para estar en un lugar amable.",
            "rit": ["Prepara el rincón antes que el libro: una manta, una lámpara, algo caliente para beber.",
                    "Ten una relectura reconfortante al alcance de la mano para los días que la necesiten.",
                    "Termina con diez minutos de calma. Sin móvil y sin empezar otro libro todavía."],
            "marks": ["Solo un capítulo más.", "Primero el té. Luego el libro.", "No molestar: leyendo."],
            "p2": "Mi rincón de lectura", "p2sub": "Lo que hace tuyo un rincón. Marca lo que tienes, rodea lo que quieres.",
            "check": ["Una manta al alcance", "Una lámpara de luz cálida", "Una bebida que siga caliente", "Un cojín para el codo",
                      "Un marcapáginas que no se caiga", "Un sitio para el libro cuando me duerma", "Una ventana o un sonido de lluvia",
                      "Una estantería a la vista", "Una relectura cerca", "Una razón para quedarme"],
            "lists": [("Relecturas que me reconfortan", 5), ("Libros para este invierno", 5), ("Para mi rincón, algún día", 3)],
        },
        "annotator": {
            "name": "El anotador", "tag": "Un libro no termina hasta que has discutido con él.",
            "body": "Lees con lápiz, no puedes prestar un libro sin un pellizco y confías más en un margen que en una reseña. Para ti una página es un lugar donde pensar, y un libro mejora con cada línea que le dejas.",
            "rit": ["Elige un bolígrafo que te guste y déjalo dentro del libro que lees.",
                    "Copia una frase a la semana en un cuaderno, con el número de página.",
                    "Relee tus propias notas antes de empezar el siguiente libro."],
            "marks": ["Subraya la línea que querrás volver a leer.", "Contesta: hazle una pregunta al libro.", "Deja una marca. Estuvo aquí, y tú también."],
            "p2": "Mi clave de anotaciones", "p2sub": "Seis símbolos bastan. Úsalos un mes y se vuelven costumbre.",
            "check": None,
            "key": [("una línea bajo el texto", "Una frase que merece guardarse"), ("?", "Una pregunta para el libro, o para mí"), ("!", "Una sorpresa, un giro, una risa"),
                    ("*", "Un favorito: volver a esto"), ("→", "Esto conecta con otra página u otro libro"), ("✓", "Estoy de acuerdo; es verdad para mí")],
            "asks": ["¿Qué esperaba aquí y qué ocurrió en cambio?", "¿Qué frase leería en voz alta?", "¿A quién le enviaría esta página?"],
            "lists": [("Frases que copié este mes", 6)],
        },
        "wanderer": {
            "name": "El viajero", "tag": "Cada libro es un billete a alguna parte.",
            "body": "Eliges un libro por el lugar donde ocurre, miras el mapa después de un buen capítulo y una novela traducida te parece un pequeño cruce de frontera. Leer es tu forma de viajar cuando no puedes y de recordar dónde has estado.",
            "rit": ["Busca el lugar en un mapa antes de empezar, aunque sea un lugar que no existe.",
                    "Lee un libro traducido por estación. Fíjate en lo que eligió el traductor.",
                    "Anota dónde leíste cada libro, además de dónde ocurre."],
            "marks": ["TARJETA DE EMBARQUE · Página ___ a página ___", "Destino: el último capítulo.", "Asiento: este sillón. Salida: ahora."],
            "p2": "La vuelta al mundo en 12 libros", "p2sub": "Un país, un libro, un mes. Elígelos a tu ritmo.",
            "check": None, "world": ("País o lugar", "Libro", "Autor/a"),
            "lists": [],
        },
    },
}
FILES = {"en": {"cozy": "reader-card-cozy", "annotator": "reader-card-annotator", "wanderer": "reader-card-wanderer"},
         "es": {"cozy": "tarjeta-lector-acogedor", "annotator": "tarjeta-lector-anotador", "wanderer": "tarjeta-lector-viajero"}}


class Card(bk.Kit):
    def __init__(self, path, tx, kind):
        super().__init__(path, letter)
        self.tx, self.kind, self.d = tx, kind, tx[kind]
        self.c.setTitle(self.d["name"] + " · " + tx["label"].title())

    def frame(self, title=None, subtitle=None):
        super().frame(title, subtitle)
        c, W, m = self.c, self.W, self.m
        c.setFillColor(bk.PAPER); c.rect(m + 6, m + 5, W - 2 * m - 12, 16, stroke=0, fill=1)
        c.setFont("Helvetica", 6.5); c.setFillColor(GOLD)
        c.drawCentredString(W / 2, m + 12, f"{self.tx['foot']}  ·  {self.page_no}")

    def wrap(self, text, font, size, width):
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if pdfmetrics.stringWidth(t, font, size) <= width: cur = t
            else: lines.append(cur); cur = w
        return lines + [cur] if cur else lines

    def para(self, text, x, y, w, size=11.5, lead=15, font="Garamond", color=INK):
        c = self.c; c.setFont(font, size); c.setFillColor(color)
        for ln in self.wrap(text, font, size, w):
            c.drawString(x, y, ln); y -= lead
        return y

    def page1(self):
        c, W, H, m, d, tx = self.c, self.W, self.H, self.m, self.d, self.tx
        x0, x1 = m + 34, W - m - 34
        self.frame()
        self.label(tx["label"], W / 2 - pdfmetrics.stringWidth(tx["label"], "Helvetica-Bold", 7.5) / 2, H - m - 40, size=7.5)
        self.smallcaps(d["name"], W / 2, H - m - 86, 34, GREEN, center=True)
        c.setFont("GaramondIt", 14); c.setFillColor(INK); c.drawCentredString(W / 2, H - m - 112, d["tag"])
        y = self.para(d["body"], x0, H - m - 150, x1 - x0, 12, 16.5)
        y -= 16
        self.smallcaps(tx["rituals"], x0, y, 15, GREEN)
        y -= 26
        for r in d["rit"]:
            c.setStrokeColor(INK); c.setLineWidth(0.7); c.rect(x0, y - 2, 9, 9)
            y = self.para(r, x0 + 20, y, x1 - x0 - 20, 11.5, 15) - 8
        y -= 8
        self.smallcaps(tx["cut"], x0, y, 15, GREEN)
        c.setFont("GaramondIt", 9.5); c.setFillColor(GOLD); c.drawString(x0, y - 15, tx["cut_hint"])
        top, gap = y - 30, 12
        bh = min(330, top - m - 46)
        bw = (x1 - x0 - 2 * gap) / 3
        for i, line in enumerate(d["marks"]):
            x = x0 + i * (bw + gap)
            c.setDash(2, 3); c.setStrokeColor(GOLD); c.setLineWidth(0.8); c.roundRect(x, top - bh, bw, bh, 8)
            c.setDash()
            c.setStrokeColor(bk.RULE); c.setLineWidth(0.5); c.line(x + 14, top - 28, x + bw - 14, top - 28)
            c.setFillColor(GOLD); c.circle(x + bw / 2, top - 15, 3.4, stroke=0, fill=1)
            yy = top - 78
            c.setFont("GaramondIt", 11.5); c.setFillColor(INK)
            for ln in self.wrap(line, "GaramondIt", 11.5, bw - 28):
                c.drawCentredString(x + bw / 2, yy, ln); yy -= 15
            c.setStrokeColor(GOLD); c.setLineWidth(0.7); c.line(x + bw / 2 - 12, top - bh + 26, x + bw / 2 + 12, top - bh + 26)
            c.setFont("Helvetica", 5.5); c.setFillColor(GOLD); c.drawCentredString(x + bw / 2, top - bh + 14, "THE BOOKS WANDERER")
        self.done()

    def page2(self):
        c, W, H, m, d, tx = self.c, self.W, self.H, self.m, self.d, self.tx
        x0, x1 = m + 34, W - m - 34
        iw = x1 - x0
        self.frame(d["p2"], d["p2sub"])
        y = self.top - 14
        if d.get("check"):
            half = (len(d["check"]) + 1) // 2
            for i, item in enumerate(d["check"]):
                col, row = divmod(i, half)
                x = x0 + col * (iw / 2)
                yy = y - row * 24
                c.setStrokeColor(INK); c.setLineWidth(0.7); c.rect(x, yy - 2, 9, 9)
                c.setFont("Garamond", 11.5); c.setFillColor(INK); c.drawString(x + 18, yy, item)
            y -= half * 24 + 14
        if d.get("key"):
            for sym, meaning in d["key"]:
                self.box(x0, y - 40, 74, 40, r=6)
                c.setFont("Garamond", 22 if len(sym) < 3 else 8.5); c.setFillColor(GREEN)
                if sym == "✓":      # the font has no check mark: draw one
                    c.setStrokeColor(GREEN); c.setLineWidth(1.8)
                    c.line(x0 + 28, y - 22, x0 + 35, y - 30); c.line(x0 + 35, y - 30, x0 + 48, y - 13)
                elif len(sym) < 3: c.drawCentredString(x0 + 37, y - 29, sym)
                else:
                    c.drawCentredString(x0 + 37, y - 24, sym); self.line(x0 + 12, y - 28, x0 + 62, GOLD, 1.1)
                c.setFont("Garamond", 12.5); c.setFillColor(INK); c.drawString(x0 + 92, y - 25, meaning)
                y -= 52
            y -= 4
            self.label("Three questions to ask a page" if tx is T["en"] else "Tres preguntas para una página", x0, y)
            y -= 8
            for q in d["asks"]:
                y = self.para("•  " + q, x0 + 4, y - 14, iw - 8, 11.5, 15)
            y -= 14
        if d.get("world"):
            cols = [x0, x0 + iw * 0.28, x0 + iw * 0.74, x1]
            for i, name in enumerate(d["world"]):
                self.label(name, cols[i] + 3, y)
            step = (y - self.m - 56) / 12
            for r in range(12):
                yy = y - 8 - (r + 1) * step + 12
                self.line(x0, yy, x1)
                c.setFont("Garamond", 12); c.setFillColor(GOLD); c.drawString(x0 - 2 if r < 9 else x0 - 6, yy + 4, "")
            c.setStrokeColor(bk.RULE); c.setLineWidth(0.4)
            for xc in cols[1:3]:
                c.line(xc - 4, y - 6, xc - 4, y - 8 - 12 * step + 12)
        for label, n in d.get("lists", []):
            self.label(label, x0, y)
            y = self.ruled(x0, y - 2, iw, n, step=21) - 10
        self.done()


def build(lang, kind, out):
    card = Card(out, T[lang], kind)
    card.page1(); card.page2(); card.c.save()


if __name__ == "__main__":
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "es"):
        for kind in ("cozy", "annotator", "wanderer"):
            build(lang, kind, out / f"{FILES[lang][kind]}.pdf")
            print(FILES[lang][kind])
