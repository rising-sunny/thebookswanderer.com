"""Square preview video from the spin loops and the underside still; 'Digital render' on every frame."""
import subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

M = Path("mock"); OUT = M / "video"; OUT.mkdir(exist_ok=True)
S, FPS = 1080, 24
SERIF = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
ITALIC = "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf"


def loop(name, times):
    frames = sorted((M / name).glob("f*.png"))
    return [Image.open(f).convert("RGB") for f in frames] * times


def zoom(src, n, z0=1.0, z1=1.10):
    im = Image.open(src).convert("RGB")
    out = []
    for i in range(n):
        z = z0 + (z1 - z0) * i / (n - 1)
        w = im.width / z
        box = ((im.width - w) / 2, (im.height - w) / 2, (im.width + w) / 2, (im.height + w) / 2)
        out.append(im.resize((S, S), Image.LANCZOS, box=box))
    return out


def caption(im, text, alpha):
    if alpha <= 0:
        return im
    d = ImageDraw.Draw(im, "RGBA"); f = ImageFont.truetype(SERIF, 44)
    w = d.textlength(text, font=f)
    dark = np.asarray(im.convert("L"))[60:130, :].mean() < 120
    col = (240, 235, 225) if dark else (50, 44, 38)
    d.text(((S - w) / 2, 70), text, font=f, fill=(*col, int(255 * alpha)))
    return im


def note(im):
    d = ImageDraw.Draw(im, "RGBA"); f = ImageFont.truetype(ITALIC, 26)
    t = "Digital render"; w = d.textlength(t, font=f)
    dark = np.asarray(im.convert("L"))[-60:, -int(w) - 50:].mean() < 120
    d.text((S - w - 30, S - 52), t, font=f, fill=(240, 235, 225, 190) if dark else (40, 36, 32, 190))
    return im


def fade_in_out(n, i, edge=10):
    return min(1.0, i / edge, (n - 1 - i) / edge)


import os
if os.getenv("PIECE") == "mandel":
    OUT = M / "video-mandel"; OUT.mkdir(exist_ok=True)
    segments = [(loop("mandel-spin", 1), "Escape time as height"),
                (zoom(M / "mandel-under.png", 3 * FPS), "z → z² + c, engraved underneath"),
                (zoom(M / "mandel-sunset.png", int(2.5 * FPS), 1.0, 1.06), "Matte sunset")]
else:
    segments = [(loop("spin-gold", 2), "Gold on matte black"),
                (zoom(M / "underside.png", 3 * FPS), "Its own equation, engraved underneath"),
                (loop("spin-rainbow", 2), "Silk rainbow")]
frames, X = [], 8                        # X frames of cross-fade between segments
for k, (seg, text) in enumerate(segments):
    seg = [caption(im.copy(), text, fade_in_out(len(seg), i, 12)) for i, im in enumerate(seg)]
    if frames:
        for j in range(X):
            a = (j + 1) / (X + 1)
            frames[-X + j] = Image.blend(frames[-X + j], seg[j], a)
        seg = seg[X:]
    frames += seg
for i, im in enumerate(frames):
    note(im).save(OUT / f"v{i:04d}.png")
target = sys.argv[1] if len(sys.argv) > 1 else "mock/hyperboloid-preview.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(OUT / "v%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow",
                "-movflags", "+faststart", "-an", target], check=True)
print(target, len(frames), "frames", round(len(frames) / FPS, 1), "s")
