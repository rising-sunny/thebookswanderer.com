"""Ad video for the two 3D prints, square (feed) and vertical (reels): title, both spins, end card."""
import subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

M = Path("mock"); FPS = 24
SERIF = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
ITALIC = "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf"
BG = (232, 227, 219); INK = (44, 38, 32)


def frames(name):
    return [Image.open(f).convert("RGB") for f in sorted((M / name).glob("f*.png"))]


def canvas(W, H, inner, top_text=None, bottom_text=None, alpha=1.0):
    s = min(W, H)
    im = inner.resize((s, s), Image.LANCZOS)
    a = np.asarray(im).astype(float)
    top_col = tuple(int(v) for v in a[:12].reshape(-1, 3).mean(0))      # the backdrop at the top edge
    bot_col = tuple(int(v) for v in a[-12:].reshape(-1, 3).mean(0))     # and at the bottom edge
    c = Image.new("RGB", (W, H), top_col)
    if H > W:
        ImageDraw.Draw(c).rectangle([0, H // 2, W, H], fill=bot_col)
    c.paste(im, ((W - s) // 2, (H - s) // 2))
    d = ImageDraw.Draw(c, "RGBA")
    for text, y, size, font in ((top_text, 0.07, 54, SERIF), (bottom_text, 0.93, 40, SERIF)):
        if text:
            f = ImageFont.truetype(font, size * W // 1080)
            w = d.textlength(text, font=f)
            d.text(((W - w) / 2, H * y - size / 2), text, font=f, fill=(*INK, int(255 * alpha)))
    f = ImageFont.truetype(ITALIC, 26 * W // 1080); t = "Digital render"; w = d.textlength(t, font=f)
    d.text((W - w - 30, H - 52), t, font=f, fill=(*INK, 180))
    return c


def card(W, H, lines, alpha=1.0):
    c = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(c, "RGBA")
    y = H / 2 - sum(s for _, s, _ in lines) * 0.75
    for text, size, font in lines:
        f = ImageFont.truetype(font, size * W // 1080); w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill=(*INK, int(255 * alpha))); y += size * 1.5
    return c


def fade(n, i, edge=8):
    return max(0.0, min(1.0, i / edge, (n - 1 - i) / edge))


def build(W, H, out):
    seq = []
    intro = [("Mathematics you can hold", 64, SERIF), ("3D printed sculptures, each with its equation engraved", 34, ITALIC)]
    seq += [card(W, H, intro, fade(36, i)) for i in range(36)]
    gold = frames("spin-gold") * 2
    seq += [canvas(W, H, im, "Hyperboloid of one sheet", "36 straight rods, one curved surface", fade(len(gold), i, 10))
            for i, im in enumerate(gold)]
    mandel = frames("mandel-spin")
    seq += [canvas(W, H, im, "The Mandelbrot set as a mountain", "Height is escape time: z → z² + c", fade(len(mandel), i, 10))
            for i, im in enumerate(mandel)]
    end = [("The Books Wanderer", 60, SERIF), ("MathRelaxing collection", 36, ITALIC),
           ("thebookswanderer.com", 40, SERIF), ("Free US shipping", 32, ITALIC)]
    seq += [card(W, H, end, min(1.0, i / 8)) for i in range(48)]
    tmp = M / f"promo-{W}x{H}"; tmp.mkdir(exist_ok=True)
    for i, im in enumerate(seq):
        im.save(tmp / f"p{i:04d}.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "p%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow",
                    "-movflags", "+faststart", "-an", out], check=True)
    print(out, len(seq), "frames", round(len(seq) / FPS, 1), "s")


build(1080, 1080, "mock/promo-3d-square.mp4")
build(1080, 1920, "mock/promo-3d-vertical.mp4")
