"""Listing images rendered from the real print files (no mockups)."""
import subprocess, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"
OUT = "/home/user/thebookswanderer.com/assets/products/color-the-fairy-tales-printed"
BG = (237, 230, 214); GREEN = (27, 55, 40); GREY = (95, 90, 80)
os.makedirs(OUT, exist_ok=True)
f = lambda n, s: ImageFont.truetype(f"{FONTS}/{n}", s)


def page(pdf, n, dpi=150):
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-f", str(n), "-l", str(n), "-singlefile", pdf, "tmp_page"], check=True)
    return Image.open("tmp_page.png").convert("RGB")


def shadowed(canvas, im, xy, blur=22, off=(10, 16)):
    sh = Image.new("RGBA", (im.width + 120, im.height + 120), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((60, 60, 60 + im.width, 60 + im.height), fill=(60, 50, 30, 90))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(sh, (xy[0] - 60 + off[0], xy[1] - 60 + off[1]), sh)
    canvas.paste(im, xy)


def pill(d, text, cy, W):
    fnt = f("Karla-700.ttf", 34); w = d.textlength(text, font=fnt)
    d.rounded_rectangle(((W - w) / 2 - 32, cy - 28, (W + w) / 2 + 32, cy + 28), radius=28, fill=GREEN)
    d.text((W / 2, cy), text, font=fnt, fill=(248, 242, 229), anchor="mm")


def headline(d, title, sub, W):
    d.text((W / 2, 95), title, font=f("Playfair-600.ttf", 58), fill=GREEN, anchor="mm")
    d.text((W / 2, 160), sub, font=f("Karla-400.ttf", 30), fill=GREY, anchor="mm")


W, H = 1200, 1500
# 1. main: the front cover
cov = Image.open("covhi-1.png").convert("RGB")
cw, ch = cov.size; trim = int(cw * 9 / 1255)
front = cov.crop((cw - trim - int(cw * 612 / 1255), trim, cw - trim, ch - trim))
front = front.resize((900, int(900 * front.height / front.width)), Image.LANCZOS)
img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
pill(d, "Printed paperback · 8.5 × 11 in · color", 85, W)
shadowed(img, front, ((W - front.width) // 2, 160))
d.text((W / 2, 160 + front.height + 75), "24 Walter Crane plates, each with its line drawing to color",
       font=f("Playfair-500i.ttf", 34), fill=GREEN, anchor="mm")
img.save(f"{OUT}/main_en.jpg", quality=88)

# 2. a spread: original colors left, yours right
interior = "color-the-fairy-tales-interior.pdf"
left, right = page(interior, 28, 110), page(interior, 29, 110)
sw = 560; left = left.resize((sw, int(sw * left.height / left.width))); right = right.resize(left.size)
img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
headline(d, "Every plate, twice", "On the left, the 1870s colors. On the right, yours.", W)
y = 300; shadowed(img, left, (W // 2 - sw - 6, y)); shadowed(img, right, (W // 2 + 6, y), off=(10, 16))
d.line((W // 2, y, W // 2, y + left.height), fill=(200, 192, 175), width=3)
d.text((W / 2, y + left.height + 80), "Bluebeard · Walter Crane, 1873", font=f("Playfair-500i.ttf", 32), fill=GREY, anchor="mm")
img.save(f"{OUT}/spread_en.jpg", quality=88)


def grid(names, suffix, title, sub, out):
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img); headline(d, title, sub, W)
    tw, th = 340, 440
    for k, n in enumerate(names):
        im = Image.open(f"final/{n}{suffix}").convert("RGB"); im.thumbnail((tw - 30, th - 30))
        tile = Image.new("RGB", (tw, th), "white"); tile.paste(im, ((tw - im.width) // 2, (th - im.height) // 2))
        x = 60 + (k % 3) * (tw + 30); y = 240 + (k // 3) * (th + 40)
        shadowed(img, tile, (x, y), blur=14, off=(6, 10))
    img.save(out, quality=88)


six = ["sleepingbeauty00cran-n2", "Beautybeast00CranA-n12", "frogprince00CranA-n6",
       "LittleRedRiding00Cran-n5", "GoodyTwoShoes00CranA-n6", "hindwood00Cran-n2"]
grid(six, "-line.png", "24 pages to color", "Eight fairy tales · one plate per page", f"{OUT}/pages_en.jpg")
grid(six, "-color.jpg", "The originals, in color", "From first editions printed in London, 1873–1876", f"{OUT}/color_en.jpg")

# 3. the back cover
back = cov.crop((trim, trim, trim + int(cw * 612 / 1255), ch - trim)).resize(front.size, Image.LANCZOS)
img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
pill(d, "The back cover", 85, W); shadowed(img, back, ((W - back.width) // 2, 160))
img.save(f"{OUT}/back_en.jpg", quality=88)
os.remove("tmp_page.png")
print(sorted(os.listdir(OUT)))
