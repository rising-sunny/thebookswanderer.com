"""Listing images for the Audubon mosaic books, rendered from the real print files (no mockups)."""
import subprocess, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import books

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"
BG = (237, 230, 214); GREY = (95, 90, 80)
INK = {"red": (120, 30, 45), "blue": (30, 55, 92)}
SLUG = {"red": "audubons-birds-red-printed", "blue": "audubons-birds-blue-printed"}
f = lambda n, s: ImageFont.truetype(f"{FONTS}/{n}", s)
W, H = 1200, 1500


def page(pdf, n, dpi=150):
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-f", str(n), "-l", str(n), "-singlefile", pdf, "tmp_page"], check=True)
    return Image.open("tmp_page.png").convert("RGB")


def shadowed(canvas, im, xy, blur=22, off=(10, 16)):
    sh = Image.new("RGBA", (im.width + 120, im.height + 120), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((60, 60, 60 + im.width, 60 + im.height), fill=(60, 50, 30, 90))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(sh, (xy[0] - 60 + off[0], xy[1] - 60 + off[1]), sh)
    canvas.paste(im, xy)


def pill(d, text, cy, ink):
    fnt = f("Karla-700.ttf", 34); w = d.textlength(text, font=fnt)
    d.rounded_rectangle(((W - w) / 2 - 32, cy - 28, (W + w) / 2 + 32, cy + 28), radius=28, fill=ink)
    d.text((W / 2, cy), text, font=fnt, fill=(248, 242, 229), anchor="mm")


def headline(d, title, sub, ink):
    d.text((W / 2, 95), title, font=f("Playfair-600.ttf", 58), fill=ink, anchor="mm")
    d.text((W / 2, 160), sub, font=f("Karla-400.ttf", 30), fill=GREY, anchor="mm")


def make(name):
    ink = INK[name]; plates = {"red": books.RED, "blue": books.BLUE}[name]
    out = f"/home/user/thebookswanderer.com/assets/products/{SLUG[name]}"; os.makedirs(out, exist_ok=True)
    cov = page(f"{name}-cover-print.pdf", 1, 200); cw, ch = cov.size
    trim = int(cw * 9 / 1218); pw = int(cw * 595.28 / 1218)
    front = cov.crop((cw - trim - pw, trim, cw - trim, ch - trim)); front = front.resize((820, int(820 * front.height / front.width)), Image.LANCZOS)
    back = cov.crop((trim, trim, trim + pw, ch - trim)).resize(front.size, Image.LANCZOS)

    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    pill(d, "Printed paperback · A4 · color", 85, ink)
    shadowed(img, front, ((W - front.width) // 2, 160))
    d.text((W / 2, 160 + front.height + 70), f"{len(plates)} Audubon birds to color by number",
           font=f("Playfair-500i.ttf", 34), fill=ink, anchor="mm")
    img.save(f"{out}/main_en.jpg", quality=88)

    # a spread: finished picture left, numbered grid right
    interior = f"{name}-interior.pdf"
    left, right = page(interior, 4, 110), page(interior, 5, 110)
    sw = 560; left = left.resize((sw, int(sw * left.height / left.width))); right = right.resize(left.size)
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    headline(d, "Every bird, as a spread", "On the left, the finished picture. On the right, the grid you color.", ink)
    y = 300; shadowed(img, left, (W // 2 - sw - 6, y)); shadowed(img, right, (W // 2 + 6, y))
    d.line((W // 2, y, W // 2, y + left.height), fill=(200, 192, 175), width=3)
    d.text((W / 2, y + left.height + 80), f"{plates[0][1]} · after Audubon, plate {plates[0][0]}",
           font=f("Playfair-500i.ttf", 32), fill=GREY, anchor="mm")
    img.save(f"{out}/spread_en.jpg", quality=88)

    # the birds
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    headline(d, f"{len(plates)} birds inside", "From The Birds of America, 1827–1838", ink)
    tw, th = 340, 400
    for k, (n, title, *_) in enumerate(plates[:9]):
        art = Image.open(f"out/{name}-{n}-art.png").convert("RGB"); art.thumbnail((tw - 30, th - 70))
        tile = Image.new("RGB", (tw, th), "white"); tile.paste(art, ((tw - art.width) // 2, 15))
        ImageDraw.Draw(tile).text((tw / 2, th - 28), title, font=f("Playfair-600.ttf", 22), fill=(40, 40, 40), anchor="mm")
        shadowed(img, tile, (60 + (k % 3) * (tw + 30), 230 + (k // 3) * (th + 30)), blur=14, off=(6, 10))
    img.save(f"{out}/birds_en.jpg", quality=88)

    # a close look at the grid, actual print detail
    grid = page(interior, 5, 300); gw, gh = grid.size
    crop = grid.crop((int(gw * 0.30), int(gh * 0.30), int(gw * 0.30) + 1000, int(gh * 0.30) + 1080))
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    headline(d, "3,100 squares per bird", "3.5 mm squares, light grey lines and numbers", ink)
    shadowed(img, crop, ((W - crop.width) // 2, 260))
    img.save(f"{out}/grid_en.jpg", quality=88)

    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    pill(d, "The back cover", 85, ink); shadowed(img, back, ((W - back.width) // 2, 160))
    img.save(f"{out}/back_en.jpg", quality=88)
    os.remove("tmp_page.png")
    print(sorted(os.listdir(out)))


if __name__ == "__main__":
    for name in sys.argv[1:] or ("red", "blue"):
        make(name)
