"""Underside engraving for the Mandelbrot tile: the iteration, the set's definition and a frame.
Same method as engrave.py (matplotlib mathtext -> 2D distance field in mm), on a 112 x 84 tile."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from scipy import ndimage as ndi

W, D, PX = 112.0, 84.0, 20
STROKE = 0.2
LINES = [  # (y in mm, text, height in mm)
    (21.0, "THE  MANDELBROT  SET", 3.6),
    (-15.0, r"$c \in M \Leftrightarrow |z_n| \leq 2\ \ \mathrm{for\ every}\ n$", 4.6),
    (-25.5, r"$z_0 = 0$", 4.2),
]


def runs(fig, ax, y, size, parts):
    """Set an equation piece by piece: (text, relative size, baseline shift in em, style).
    A subscript and the exponent after it share one x position, as in print."""
    pt = 72 / 25.4
    r = fig.canvas.get_renderer()
    widths, x, prev = [], 0.0, None
    placed = []
    for text, rel, dy, style in parts:
        t = ax.text(0, 0, text, fontsize=size * rel * pt, family="STIXGeneral", style=style)
        bb = t.get_window_extent(renderer=r); t.remove()
        w = bb.width / fig.dpi * 25.4
        if prev and prev[1] < 1 and rel < 1 and dy > 0:      # exponent stacked over the subscript
            placed.append((text, rel, dy, style, prev[0]))
            x = max(x, prev[0] + w)
        else:
            placed.append((text, rel, dy, style, x))
            prev = (x, rel); x += w
    for text, rel, dy, style, px in placed:
        ax.text(px - x / 2, y + dy * size * 0.75, text, fontsize=size * rel * pt, family="STIXGeneral",
                style=style, va="baseline", ha="left")


def mask():
    plt.rcParams["mathtext.fontset"] = "stix"
    fig = plt.figure(figsize=(W / 25.4, D / 25.4), dpi=PX * 25.4)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(-W / 2, W / 2); ax.set_ylim(-D / 2, D / 2); ax.axis("off")
    pt = 72 / 25.4
    for y, text, size in LINES:
        ax.text(0, y, text, ha="center", va="center", fontsize=size * pt, family="STIXGeneral")
    runs(fig, ax, 3.0, 10.0, [("z", 1, 0, "italic"), ("n+1", .5, -.32, "italic"), ("  =  ", 1, 0, "normal"),
                              ("z", 1, 0, "italic"), ("n", .5, -.32, "italic"), ("2", .5, .62, "normal"),
                              ("  +  ", 1, 0, "normal"), ("c", 1, 0, "italic")])
    ax.add_patch(FancyBboxPatch((-W / 2 + 6, -D / 2 + 6), W - 12, D - 12, boxstyle="round,pad=0,rounding_size=3",
                                fill=False, lw=0.7 * pt, ec="k"))
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., 0]
    plt.close(fig)
    return img < 128


INK = ndi.distance_transform_edt(~mask()) / PX <= STROKE
SDF2 = np.where(INK, -ndi.distance_transform_edt(INK) / PX, ndi.distance_transform_edt(~INK) / PX).astype(np.float32)


def text2d(x, y):
    """Distance (mm) to the lettering as seen from below: x is mirrored."""
    col = (-x + W / 2) * PX
    row = (D / 2 - y) * PX
    return ndi.map_coordinates(SDF2, [row, col], order=1, mode="nearest")


if __name__ == "__main__":
    from PIL import Image
    t = ndi.distance_transform_edt(INK) / PX
    ridge = (t == ndi.maximum_filter(t, 3)) & INK & (t > 0.05)
    print("thinnest stroke ~ %.2f mm" % (2 * np.percentile(t[ridge], 2)))
    Image.fromarray(np.where(INK, 30, 235).astype(np.uint8)).save("engrave-tile.png")
