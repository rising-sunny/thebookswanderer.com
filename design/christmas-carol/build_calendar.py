"""2027 wall calendar from the 1843 (John Leech) and 1915 (Arthur Rackham) illustrations of A Christmas Carol.

  python build_calendar.py SRC OUT     # SRC: folder with plates rN-NNN.jpg (Rackham) / lN-NNN.jpg (Leech) from the
                                        # Internet Archive scans; OUT: folder for front_cover.jpg, january.jpg..december.jpg, back_cover.jpg
                                        # (3375 x 2625 px = Printify's 11 x 8.5 in calendar art pages with bleed; the date
                                        # grids are printed by Printify, so these pages carry only art and quote)

Both illustrators and Dickens's text are public domain. Quotes are verbatim from Project Gutenberg #46.
"""
import calendar
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

W, H = 3375, 2625  # Printify calendar art page, 11 x 8.5 in plus bleed, at 300 ppi
PAPER, INK, RED, GREEN, MUTE = (247, 240, 224), (52, 40, 32), (150, 38, 38), (46, 82, 58), (140, 120, 100)
FONTS = Path(__file__).parent / "fonts"

# (plate file, stave, quote)
MONTHS = [
    ("r8-008", "Stave I", "“I wear the chain I forged in life. I made it link by link, and yard by yard.”"),
    ("r41-041", "Stave I", "Nobody under the bed; nobody in the closet; nobody in his dressing-gown, which was hanging up in a suspicious attitude against the wall."),
    ("r55-055", "Stave I", "The air was filled with phantoms, wandering hither and thither in restless haste, and moaning as they went."),
    ("r35-035", "Stave I", "…the clerk… went down a slide on Cornhill, at the end of a lane of boys, twenty times, in honour of its being Christmas Eve."),
    ("r131-131", "Stave III", "The way he went after that plump sister in the lace tucker, was an outrage on the credulity of human nature."),
    ("r79-079", "Stave II", "Then old Fezziwig stood out to dance with Mrs. Fezziwig."),
    ("r89-089", "Stave III", "…the centre of a flushed and boisterous group, just in time to greet the father, who came home attended by a man laden with Christmas toys and presents."),
    ("r93-093", "Stave III", "Then the shouting and the struggling, and the onslaught that was made on the defenceless porter!"),
    ("l40-040", "Stave I", "“Mankind was my business. The common welfare was my business; charity, mercy, forbearance, and benevolence, were, all, my business.”"),
    ("r147-147", "Stave IV", "“Well!” said the first. “Old Scratch has got his own at last, hey?”"),
    ("r155-155", "Stave IV", "“What do you call this?” said Joe. “Bed-curtains!”"),
    ("l8-008", "Stave V", "He knew how to keep Christmas well, if any man alive possessed the knowledge. May that be truly said of us, and all of us! And so, as Tiny Tim observed, God bless Us, Every One!"),
]


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def plate(src, name):
    im = Image.open(Path(src) / f"{name}.jpg").convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((8, 8)))
    box = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 38 else 0).getbbox()
    if name.startswith("l"):  # Leech: drop the publisher's imprint line under the signature
        box = (box[0], box[1], box[2], box[1] + int((box[3] - box[1]) * 0.93))
    pad = 24
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad), min(im.height, box[3] + pad))
    return im.crop(box)


def fit(im, w, h):
    s = min(w / im.width, h / im.height)
    return im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)


def wrap(d, text, f, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


def month_page(src, idx, spec):
    name, stave, quote = spec
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    art = fit(plate(src, name), 1700, 2250)
    x0, y0 = 150, (H - art.height) // 2
    img.paste(art, (x0, y0))
    d.rectangle([x0 - 1, y0 - 1, x0 + art.width, y0 + art.height], outline=MUTE, width=3)
    rx, rw = x0 + art.width + 170, W - 150 - (x0 + art.width + 170)
    d.text((rx, 150), calendar.month_name[idx].upper(), font=font("eb-500-normal.woff", 150), fill=GREEN)
    d.text((rx + rw, 255), "2027", font=font("eb-400-normal.woff", 70), fill=RED, anchor="ra")
    d.line([rx, 345, rx + rw, 345], fill=RED, width=4)
    fq, ff = font("eb-400-italic.woff", 78), font("eb-400-normal.woff", 44)
    lines = wrap(d, quote, fq, rw)
    y = max(520, H // 2 - (len(lines) * 100 + 90) // 2 - 80)
    d.line([rx, y - 40, rx + 200, y - 40], fill=RED, width=4)
    for ln in lines:
        d.text((rx, y), ln, font=fq, fill=INK)
        y += 100
    d.text((rx, y + 30), f"CHARLES DICKENS · A CHRISTMAS CAROL · {stave.upper()}", font=ff, fill=MUTE)
    credit = "Illustration: " + ("John Leech, 1843" if name.startswith("l") else "Arthur Rackham, 1915") + " · public domain"
    d.text((rx, H - 190), credit, font=font("eb-400-normal.woff", 38), fill=MUTE)
    return img


def cover(src):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    art = fit(plate(src, "l93-093"), 1700, 2250)
    x0 = 150
    img.paste(art, (x0, (H - art.height) // 2))
    rx = x0 + art.width + 170
    rw = W - 150 - rx
    d.text((rx, 520), "A CHRISTMAS", font=font("eb-500-normal.woff", 170), fill=GREEN)
    d.text((rx, 720), "CAROL", font=font("eb-500-normal.woff", 170), fill=GREEN)
    d.line([rx, 960, rx + rw, 960], fill=RED, width=5)
    d.text((rx, 1020), "Wall Calendar 2027", font=font("eb-400-italic.woff", 90), fill=RED)
    d.text((rx, 1180), "Twelve illustrations by John Leech (1843)", font=font("eb-400-normal.woff", 54), fill=INK)
    d.text((rx, 1260), "and Arthur Rackham (1915), each with a line", font=font("eb-400-normal.woff", 54), fill=INK)
    d.text((rx, 1340), "from Charles Dickens’s story.", font=font("eb-400-normal.woff", 54), fill=INK)
    return img


def back():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    art = fit(plate(SRC_DIR, "l169-169"), 1500, 2000)
    img.paste(art, ((W - art.width) // 2, 200))
    d.text((W // 2, 2330), "God bless Us, Every One!", font=font("eb-400-italic.woff", 90), fill=RED, anchor="ma")
    d.text((W // 2, 2470), "Illustrations: John Leech (1843) and Arthur Rackham (1915) \u00b7 public domain", font=font("eb-400-normal.woff", 40), fill=MUTE, anchor="ma")
    return img


SRC_DIR = "."

if __name__ == "__main__":
    SRC_DIR = sys.argv[1]
    src, out = SRC_DIR, Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    save = dict(quality=88, subsampling=0, dpi=(300, 300))
    cover(src).save(out / "front_cover.jpg", **save)
    for i, spec in enumerate(MONTHS, 1):
        month_page(src, i, spec).save(out / f"{calendar.month_name[i].lower()}.jpg", **save)
    back().save(out / "back_cover.jpg", **save)
