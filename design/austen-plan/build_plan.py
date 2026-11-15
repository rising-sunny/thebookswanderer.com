"""Free lead magnet: "Read Jane Austen in 2027", a six-novel reading plan (EN: US Letter, ES: A4).

  python build_plan.py FONTS_DIR OUT_DIR   # FONTS_DIR needs EBGaramond.ttf and EBGaramond-Italic.ttf
                                           # writes jane-austen-reading-plan-2027.pdf and plan-de-lectura-jane-austen-2027.pdf

Chapter counts are the standard ones for the first editions' chapter divisions:
Sense and Sensibility 50, Pride and Prejudice 61, Mansfield Park 48, Emma 55, Northanger Abbey 31, Persuasion 24.
Same look as the free 2027 challenge PDF (EB Garamond, green and gold).
"""
import sys
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONTS = Path(sys.argv[1])
OUT = Path(sys.argv[2])
pdfmetrics.registerFont(TTFont("Garamond", str(FONTS / "EBGaramond.ttf")))
pdfmetrics.registerFont(TTFont("GaramondIt", str(FONTS / "EBGaramond-Italic.ttf")))
GREEN, GOLD, INK, RULE, SOFT = (HexColor(c) for c in ("#233f33", "#9a7b3c", "#2a2622", "#c9bfae", "#f3ecdc"))

START = date(2027, 1, 4)          # a Monday
# (key, chapters, weeks, published)
PLAN = [("pp", 61, 9, 1813), ("ss", 50, 8, 1811), ("emma", 55, 9, 1815),
        ("mp", 48, 8, 1814), ("na", 31, 5, 1817), ("pers", 24, 4, 1817)]

TEXT = {
    "en": {
        "out": "jane-austen-reading-plan-2027.pdf", "page": letter,
        "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "day": lambda m, d: f"{m} {d}",
        "title": "Read Jane Austen in 2027", "sub": "Six novels, one plan, a rest week between each",
        "intro": ("Jane Austen finished six novels. Read at the pace of about six chapters a week, all six fit into "
                  "2027 with room to spare. This plan starts with Pride and Prejudice, in the year a new adaptation "
                  "arrives, and ends with Persuasion, her last complete novel. Change the order if you like: the "
                  "weekly targets work in any sequence."),
        "how_t": "How it works",
        "how": ["Each novel gets a handful of weeks. The grid on the next pages gives you the chapters to read each week.",
                "After every novel there is one week off. Use it to rest, to reread a favourite chapter or to watch an adaptation.",
                "Behind schedule? Skip ahead, not back. A week of three chapters still counts."],
        "glance": "The six at a glance",
        "cols": ["Novel", "Published", "Chapters", "Weeks", "Chapters a week", "Dates"],
        "titles": {"pp": "Pride and Prejudice", "ss": "Sense and Sensibility", "emma": "Emma",
                   "mp": "Mansfield Park", "na": "Northanger Abbey", "pers": "Persuasion"},
        "pubnote": {"na": "1817*", "pers": "1817*"},
        "pubfoot": "* Northanger Abbey and Persuasion came out together in December 1817; their title pages say 1818.",
        "wk": "Week", "ch": "ch.", "tick": "tick when done",
        "sched": "Your weekly schedule",
        "notice_t": "What to notice",
        "notice": {
            "pp": "First impressions: note every time someone judges another person on sight, then see who was right.",
            "ss": "Keep two columns: what Elinor holds back and what Marianne says out loud.",
            "emma": "Watch the narrator: when does she let us see Emma's mistakes before Emma does?",
            "mp": "Fanny is mostly quiet. Notice what she sees in the scenes where she says nothing.",
            "na": "A parody of Gothic novels. Spot every moment where Catherine's reading colours what she sees.",
            "pers": "Listen for the quiet: what is said, and what is only remembered.",
        },
        "free_t": "The last weeks",
        "free": "Weeks 49 to 52 are free. Reread the novel you liked best, or start a seventh book.",
        "read_t": "Where to read them free",
        "read": ("All six novels are in the public domain. You can read or download them for free on Project Gutenberg "
                 "(gutenberg.org) and Standard Ebooks (standardebooks.org), or borrow them from your library."),
        "foot": "Free for personal use · The Books Wanderer · thebookswanderer.com",
        "more": "Want to read Pride and Prejudice alongside a screen version? The Pride and Prejudice Watch Party Kit has a "
                "nine-week plan, a who-is-who page and bingo cards: thebookswanderer.com/products/pride-and-prejudice-watch-party-kit",
    },
    "es": {
        "out": "plan-de-lectura-jane-austen-2027.pdf", "page": A4,
        "months": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
        "day": lambda m, d: f"{d} {m}",
        "title": "Lee a Jane Austen en 2027", "sub": "Seis novelas, un plan y una semana de descanso entre cada una",
        "intro": ("Jane Austen terminó seis novelas. Leídas a un ritmo de unos seis capítulos por semana, caben todas en "
                  "2027 con margen. Este plan empieza con Orgullo y prejuicio, el año en que llega una nueva adaptación, "
                  "y termina con Persuasión, su última novela completa. Cambia el orden si quieres: las metas semanales "
                  "sirven en cualquier secuencia."),
        "how_t": "Cómo funciona",
        "how": ["Cada novela tiene unas semanas. La cuadrícula de las páginas siguientes te da los capítulos de cada semana.",
                "Después de cada novela hay una semana libre. Úsala para descansar, releer un capítulo que te gustó o ver una adaptación.",
                "¿Vas atrasado? Salta hacia delante, no hacia atrás. Una semana de tres capítulos también cuenta."],
        "glance": "Las seis de un vistazo",
        "cols": ["Novela", "Publicada", "Capítulos", "Semanas", "Cap. por semana", "Fechas"],
        "titles": {"pp": "Orgullo y prejuicio", "ss": "Sentido y sensibilidad", "emma": "Emma",
                   "mp": "Mansfield Park", "na": "La abadía de Northanger", "pers": "Persuasión"},
        "pubnote": {"na": "1817*", "pers": "1817*"},
        "pubfoot": "* La abadía de Northanger y Persuasión salieron juntas en diciembre de 1817; sus portadas dicen 1818.",
        "wk": "Semana", "ch": "cap.", "tick": "marca al terminar",
        "sched": "Tu calendario semanal",
        "notice_t": "En qué fijarse",
        "notice": {
            "pp": "Las primeras impresiones: anota cada vez que alguien juzga a otro a primera vista y mira quién tenía razón.",
            "ss": "Lleva dos columnas: lo que Elinor se calla y lo que Marianne dice en voz alta.",
            "emma": "Observa a la narradora: ¿cuándo nos deja ver los errores de Emma antes que la propia Emma?",
            "mp": "Fanny casi no habla. Fíjate en lo que ve en las escenas en que no dice nada.",
            "na": "Una parodia de las novelas góticas. Detecta cada momento en que las lecturas de Catherine tiñen lo que ve.",
            "pers": "Escucha el silencio: lo que se dice y lo que solo se recuerda.",
        },
        "free_t": "Las últimas semanas",
        "free": "Las semanas 49 a 52 quedan libres. Relee la novela que más te gustó o empieza un séptimo libro.",
        "read_t": "Dónde leerlas gratis",
        "read": ("Las seis novelas son de dominio público. Puedes leerlas o descargarlas gratis en Project Gutenberg "
                 "(gutenberg.org) y Standard Ebooks (standardebooks.org), o pedirlas prestadas en tu biblioteca. "
                 "Los textos originales están en inglés."),
        "foot": "Gratis para uso personal · The Books Wanderer · thebookswanderer.com",
        "more": "",
    },
}


def schedule():
    """[(key, chapters, weeks, [(week_no, monday, first_ch, last_ch)...], first_monday, last_monday)]"""
    out, week = [], 0
    for key, chapters, weeks, _ in PLAN:
        base, extra = divmod(chapters, weeks)
        rows, ch = [], 1
        for i in range(weeks):
            n = base + (1 if i < extra else 0)
            week += 1
            rows.append((week, START + timedelta(weeks=week - 1), ch, ch + n - 1)); ch += n
        out.append((key, chapters, weeks, rows))
        week += 1                                        # a rest week after each novel
    return out


def wrap(c, text, x, y, width, font="Garamond", size=11, lead=14.5, color=INK):
    c.setFont(font, size); c.setFillColor(color)
    for line in simpleSplit(text, font, size, width):
        c.drawString(x, y, line); y -= lead
    return y


def build(lang):
    t = TEXT[lang]
    W, H = t["page"]
    M = 60
    CW = W - 2 * M
    sched = schedule()
    c = canvas.Canvas(str(OUT / t["out"]), pagesize=t["page"], initialFontName="Garamond", initialFontSize=11)
    c.setTitle(t["title"]); c.setAuthor("The Books Wanderer")
    fmt = lambda d: t["day"](t["months"][d.month - 1], d.day)

    def footer():
        c.setFont("GaramondIt", 9); c.setFillColor(GOLD); c.drawCentredString(W / 2, 34, t["foot"])

    def heading(text, y, size=17):
        c.setFont("Garamond", size); c.setFillColor(GREEN); c.drawString(M, y, text)
        c.setStrokeColor(GOLD); c.setLineWidth(0.8); c.line(M, y - 5, M + CW, y - 5)
        return y - 26

    # ---- page 1
    c.setFillColor(GREEN); c.rect(0, H - 150, W, 150, stroke=0, fill=1)
    c.setFillColor(HexColor("#faf5e9")); c.setFont("Garamond", 38); c.drawString(M, H - 82, t["title"])
    c.setFillColor(HexColor("#d9bf7a")); c.setFont("GaramondIt", 16); c.drawString(M, H - 112, t["sub"])
    y = wrap(c, t["intro"], M, H - 186, CW, size=12, lead=16.5)
    y = heading(t["how_t"], y - 14)
    for i, item in enumerate(t["how"], 1):
        c.setFont("Garamond", 15); c.setFillColor(GOLD); c.drawString(M, y, str(i))
        y = wrap(c, item, M + 20, y, CW - 20, size=11.5, lead=15) - 5
    y = heading(t["glance"], y - 12)
    xs = [M, M + 150, M + 215, M + 268, M + 318, M + 400]
    c.setFont("GaramondIt", 9.5); c.setFillColor(GOLD)
    for x, col in zip(xs, t["cols"]):
        c.drawString(x, y, col)
    y -= 6; c.setStrokeColor(RULE); c.setLineWidth(0.5); c.line(M, y, M + CW, y); y -= 15
    for key, chapters, weeks, rows in sched:
        pub = t["pubnote"].get(key, str([p for k, _, _, p in PLAN if k == key][0]))
        per = f"{chapters / weeks:.1f}".rstrip("0").rstrip(".")
        vals = [t["titles"][key], pub, str(chapters), str(weeks), per, f"{fmt(rows[0][1])} – {fmt(rows[-1][1] + timedelta(days=6))}"]
        c.setFont("Garamond", 11); c.setFillColor(INK)
        for i, (x, v) in enumerate(zip(xs, vals)):
            c.drawString(x, y, v)
        y -= 19; c.setStrokeColor(RULE); c.line(M, y + 12, M + CW, y + 12)
    wrap(c, t["pubfoot"], M, y - 2, CW, font="GaramondIt", size=9, lead=12, color=INK)
    if t["more"]:
        wrap(c, t["more"], M, 88, CW, font="GaramondIt", size=9.5, lead=12.5, color=GREEN)
    footer(); c.showPage()

    # ---- pages 2 and 3: the weekly grid, three novels per page
    def grid_page(chunk, notice_extra=False):
        y = heading(t["sched"], H - 64)
        for key, chapters, weeks, rows in chunk:
            c.setFont("Garamond", 14); c.setFillColor(GREEN)
            c.drawString(M, y, f"{t['titles'][key]}"); c.setFont("GaramondIt", 10); c.setFillColor(GOLD)
            c.drawRightString(M + CW, y, f"{chapters} {t['ch']} · {fmt(rows[0][1])} – {fmt(rows[-1][1] + timedelta(days=6))}")
            y -= 10
            per_row = 5 if weeks > 5 else weeks
            bw, bh = CW / 5, 40
            for i, (wn, monday, a, b) in enumerate(rows):
                col, row = i % 5, i // 5
                x0, y0 = M + col * bw, y - row * (bh + 4)
                c.setFillColor(SOFT); c.setStrokeColor(RULE); c.setLineWidth(0.5)
                c.roundRect(x0 + 2, y0 - bh, bw - 4, bh, 3, stroke=1, fill=1)
                c.setFillColor(INK); c.setFont("Garamond", 9); c.drawString(x0 + 8, y0 - 12, f"{t['wk']} {wn} · {fmt(monday)}")
                c.setFont("Garamond", 12.5); c.setFillColor(GREEN)
                c.drawString(x0 + 8, y0 - 29, f"{t['ch']} {a}–{b}" if b > a else f"{t['ch']} {a}")
                c.setStrokeColor(GOLD); c.setLineWidth(0.8); c.rect(x0 + bw - 22, y0 - 31, 11, 11, stroke=1, fill=0)
            rows_n = (weeks + 4) // 5
            y -= rows_n * (bh + 4) + 4
            y = wrap(c, f"{t['notice_t']}: {t['notice'][key]}", M, y - 4, CW, font="GaramondIt", size=10, lead=13, color=INK) - 14
        return y

    grid_page(sched[:3]); footer(); c.showPage()
    y = grid_page(sched[3:])
    y = heading(t["free_t"], y - 8, size=15)
    y = wrap(c, t["free"], M, y, CW, size=11.5, lead=15) - 12
    y = heading(t["read_t"], y - 6, size=15)
    y = wrap(c, t["read"], M, y, CW, size=11.5, lead=15)
    footer(); c.showPage()
    c.save()
    print(OUT / t["out"], sched[-1][3][-1][1] + timedelta(days=6))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "es"):
        build(lang)
