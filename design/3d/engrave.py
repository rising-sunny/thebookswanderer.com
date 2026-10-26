"""Engraving for the underside of the plinth: the surface's own equation and its name.
Drawn with matplotlib mathtext, turned into a 2D distance field in mm and cut 0.6 mm deep.

The rods are straight lines from radius R at the foot to a point turned 120 degrees at the
top, so the surface they rule is x^2/a^2 + y^2/a^2 - z^2/c^2 = 1 with
a = R cos 60 = 16 mm and c^2 = a^2 h^2 / (R^2 - a^2) = 675, c = 15 sqrt 3 mm (h = 45 mm)."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import ndimage as ndi

SIZE, PX = 84.0, 20                       # field of 84 mm, 20 px per mm
EQ = r"$\frac{x^2}{16^2}+\frac{y^2}{16^2}-\frac{z^2}{(15\sqrt{3})^2}=1$"
NAME = "HYPERBOLOID OF ONE SHEET"
STROKE = 0.2                             # mm added around each glyph so no line is a hairline


def text_mask():
    plt.rcParams["mathtext.fontset"] = "stix"
    fig = plt.figure(figsize=(SIZE / 25.4,) * 2, dpi=PX * 25.4)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(-SIZE / 2, SIZE / 2); ax.set_ylim(-SIZE / 2, SIZE / 2); ax.axis("off")
    pt = 72 / 25.4                        # points per mm
    ax.text(0, -3, EQ, ha="center", va="center", fontsize=6.6 * pt, family="STIXGeneral")
    ax.add_patch(plt.Circle((0, 0), 38.2, fill=False, lw=0.7 * pt, color="k"))   # a thin border ring
    # the name runs round the edge, reading clockwise along the top
    r, span = 33.0, np.radians(128)
    w = np.array([0.55 if ch == " " else 1.0 for ch in NAME])     # a space is narrower than a letter
    pos = np.cumsum(w) - w / 2; pos = (pos - pos[0]) / (pos[-1] - pos[0])
    for ch, f in zip(NAME, pos):
        if ch == " ":
            continue
        a = np.pi / 2 + span / 2 - span * f
        ax.text(r * np.cos(a), r * np.sin(a), ch, ha="center", va="center", rotation=np.degrees(a) - 90,
                fontsize=3.4 * pt, family="STIXGeneral")
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., 0]
    plt.close(fig)
    return img < 128                      # True where ink


def field():
    ink = text_mask()
    ink = ndi.distance_transform_edt(~ink) / PX <= STROKE
    inside = ndi.distance_transform_edt(ink) / PX
    outside = ndi.distance_transform_edt(~ink) / PX
    return np.where(ink, -inside, outside).astype(np.float32), ink


SDF2, INK = field()


def text2d(x, y):
    """Signed distance (mm) to the lettering, as seen from below: x is mirrored."""
    n = SDF2.shape[0]
    col = (-x + SIZE / 2) * PX            # mirrored so it reads right when the piece is turned over
    row = (SIZE / 2 - y) * PX
    return ndi.map_coordinates(SDF2, [row, col], order=1, mode="nearest")


if __name__ == "__main__":
    from PIL import Image
    t = ndi.distance_transform_edt(INK) / PX
    ridge = (t == ndi.maximum_filter(t, 3)) & INK & (t > 0.05)
    print("thinnest stroke ~ %.2f mm" % (2 * np.percentile(t[ridge], 2)))
    gap = ndi.distance_transform_edt(~INK) / PX
    print("ink fits within radius %.1f mm" % np.hypot(*(np.argwhere(INK) / PX - SIZE / 2).T).max())
    Image.fromarray(np.where(INK, 30, 235).astype(np.uint8)).save("engrave-flat.png")
