"""Engravings for the Gabriel's horn plinth: a ring of text on top, read from outside, and a note underneath."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import ndimage as ndi

SIZE, PX, STROKE = 104.0, 20, 0.2
RING = "GABRIEL'S HORN   ·   y = 1/x,  x ≥ 1   ·   V = π   ·   A = ∞"


def _canvas():
    plt.rcParams["mathtext.fontset"] = "stix"
    fig = plt.figure(figsize=(SIZE / 25.4,) * 2, dpi=PX * 25.4)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(-SIZE / 2, SIZE / 2); ax.set_ylim(-SIZE / 2, SIZE / 2); ax.axis("off")
    return fig, ax


def _field(fig):
    fig.canvas.draw()
    ink = np.asarray(fig.canvas.buffer_rgba())[..., 0] < 128
    plt.close(fig)
    ink = ndi.distance_transform_edt(~ink) / PX <= STROKE
    return np.where(ink, -ndi.distance_transform_edt(ink) / PX, ndi.distance_transform_edt(~ink) / PX).astype(np.float32), ink


def ring_text(r=44.6, size=4.3):
    """Letters set round the front of the circle, tops toward the centre, read from in front."""
    fig, ax = _canvas()
    pt = 72 / 25.4
    r_ = fig.canvas.get_renderer()
    widths = []
    for ch in RING:
        t = ax.text(0, 0, ch, fontsize=size * pt, family="STIXGeneral"); bb = t.get_window_extent(renderer=r_); t.remove()
        widths.append(max(bb.width / fig.dpi * 25.4, size * 0.3))
    gap = size * 0.12                                  # a little tracking between letters
    total = sum(widths) + gap * len(widths)
    a = 3 * np.pi / 2 - total / 2 / r                  # centred on the front, read left to right
    for ch, w in zip(RING, widths):
        a_mid = a + (w + gap) / 2 / r
        ax.text(r * np.cos(a_mid), r * np.sin(a_mid), ch, ha="center", va="center", rotation=np.degrees(a_mid) + 90,
                fontsize=size * pt, family="STIXGeneral")
        a += (w + gap) / r
    return _field(fig)


def under_text():
    fig, ax = _canvas()
    pt = 72 / 25.4
    lines = [(14, "Finite volume, infinite surface", 4.2, "italic"),
             (2, r"$V=\pi\int_1^{\infty}\frac{dx}{x^2}=\pi$", 6.0, "normal"),
             (-12, r"$A\geq 2\pi\int_1^{\infty}\frac{dx}{x}=\infty$", 6.0, "normal"),
             (-26, "Evangelista Torricelli, 1643", 3.6, "italic")]
    for y, text, s, style in lines:
        ax.text(0, y, text, ha="center", va="center", fontsize=s * pt, family="STIXGeneral", style=style)
    ax.add_patch(plt.Circle((0, 0), 47.5, fill=False, lw=0.7 * pt, color="k"))
    return _field(fig)


TOP, TOP_INK = ring_text()
UNDER, UNDER_INK = under_text()


def sample(field, x, y, mirror=False):
    col = ((-x if mirror else x) + SIZE / 2) * PX
    row = (SIZE / 2 - y) * PX
    return ndi.map_coordinates(field, [row, col], order=1, mode="nearest")


if __name__ == "__main__":
    from PIL import Image
    for name, ink in (("top", TOP_INK), ("under", UNDER_INK)):
        t = ndi.distance_transform_edt(ink) / PX
        ridge = (t == ndi.maximum_filter(t, 3)) & ink & (t > 0.05)
        print(name, "thinnest stroke ~ %.2f mm" % (2 * np.percentile(t[ridge], 2)))
        Image.fromarray(np.where(ink, 30, 235).astype(np.uint8)).save(f"engrave-horn-{name}.png")
