"""Colour previews of the hyperboloid in the Slant filaments we quoted."""
import colorsys, numpy as np
from PIL import Image
from render_sdf import render

def rainbow(p):
    # silk rainbow filament shifts hue as the print climbs, roughly one cycle over this piece
    hue = (p[:, 2] / 103.0 * 0.95 + 0.0) % 1
    base = np.array([colorsys.hsv_to_rgb(h, 0.62, 0.92) for h in hue])
    return base, np.full(len(p), 0.9)

def gold_black(p):
    plinth = p[:, 2] < 7.05
    base = np.where(plinth[:, None], np.array([0.09, 0.09, 0.10]), np.array([0.83, 0.64, 0.27]))
    return base, np.where(plinth, 0.08, 1.0)

a = render("hyperboloid_strong", S=640, paint=rainbow)
b = render("hyperboloid_duo", S=640, paint=gold_black)
a.save("c-rainbow.png"); b.save("c-gold-black.png")
w = Image.new("RGB", (1280, 640)); w.paste(a, (0, 0)); w.paste(b, (640, 0)); w.save("c-both.png")
