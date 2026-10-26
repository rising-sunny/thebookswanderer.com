"""Listing images for The Jane Austen Puzzle Book, rendered from the print files (no mockups)."""
import os, subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"
OUT = "/home/user/thebookswanderer.com/assets/products/jane-austen-puzzle-book"
BG = (237, 230, 214); INK = (38, 52, 44); GREY = (95, 90, 80)
f = lambda n, s: ImageFont.truetype(f"{FONTS}/{n}", s)
W, H = 1200, 1500
os.makedirs(OUT, exist_ok=True)


def page(pdf, n, dpi=110):
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(n), "-l", str(n), "-png", "-singlefile", pdf, "tmp_page"], check=True)
    return Image.open("tmp_page.png").convert("RGB")


def shadowed(c, im, xy, blur=22, off=(10, 16)):
    sh = Image.new("RGBA", (im.width + 120, im.height + 120), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((60, 60, 60 + im.width, 60 + im.height), fill=(60, 50, 30, 90))
    sh = sh.filter(ImageFilter.GaussianBlur(blur)); c.paste(sh, (xy[0] - 60 + off[0], xy[1] - 60 + off[1]), sh); c.paste(im, xy)


def headline(d, t, s):
    d.text((W / 2, 95), t, font=f("Playfair-600.ttf", 58), fill=INK, anchor="mm")
    d.text((W / 2, 160), s, font=f("Karla-400.ttf", 30), fill=GREY, anchor="mm")


cov = page("austen-cover.pdf", 1, 200); cw, ch = cov.size
trim = int(cw * 9 / 1259); pw = int(cw * 612 / 1259)
front = cov.crop((cw - trim - pw, trim, cw - trim, ch - trim)); front = front.resize((820, int(820 * front.height / front.width)), Image.LANCZOS)
back = cov.crop((trim, trim, trim + pw, ch - trim)).resize(front.size, Image.LANCZOS)

img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
fnt = f("Karla-700.ttf", 34); t = "Printed paperback · 8.5 × 11 in · 76 pages"; w = d.textlength(t, font=fnt)
d.rounded_rectangle(((W - w) / 2 - 32, 57, (W + w) / 2 + 32, 113), radius=28, fill=INK); d.text((W / 2, 85), t, font=fnt, fill=(248, 242, 229), anchor="mm")
shadowed(img, front, ((W - front.width) // 2, 160))
d.text((W / 2, 160 + front.height + 70), "54 puzzles from Jane Austen's six novels", font=f("Playfair-500i.ttf", 34), fill=INK, anchor="mm")
img.save(f"{OUT}/main_en.jpg", quality=88)

pdf = "austen-interior.pdf"
img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
headline(d, "Nine puzzles for every novel", "Word searches, cryptograms, crossword, quotes and a quiz")
tw = 340
for k, n in enumerate((6, 7, 8, 9, 12, 14)):
    pg = page(pdf, n, 80); pg = pg.resize((tw, int(tw * 11 / 8.5)), Image.LANCZOS)
    shadowed(img, pg, (60 + (k % 3) * (tw + 30), 240 + (k // 3) * (pg.height + 40)), blur=14, off=(6, 10))
img.save(f"{OUT}/pages_en.jpg", quality=88)

for name, n, title, sub in (("crossword", 8, "A crossword for each book", "Names, places and things from the novel"),
                            ("quotes", 9, "Who said it?", "Every line checked against Austen's own text")):
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img); headline(d, title, sub)
    pg = page(pdf, n, 130); pg = pg.resize((900, int(900 * 11 / 8.5)), Image.LANCZOS).crop((0, 0, 900, 1130))
    shadowed(img, pg, ((W - 900) // 2, 250))
    img.save(f"{OUT}/{name}_en.jpg", quality=88)

img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
fnt = f("Karla-700.ttf", 34); t = "The back cover"; w = d.textlength(t, font=fnt)
d.rounded_rectangle(((W - w) / 2 - 32, 57, (W + w) / 2 + 32, 113), radius=28, fill=INK); d.text((W / 2, 85), t, font=fnt, fill=(248, 242, 229), anchor="mm")
shadowed(img, back, ((W - back.width) // 2, 160)); img.save(f"{OUT}/back_en.jpg", quality=88)
os.remove("tmp_page.png"); print(sorted(os.listdir(OUT)))
