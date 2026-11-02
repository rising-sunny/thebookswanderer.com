"""Four fractal Christmas ornaments as flat 2D shapes (mm), each with a hanging loop.

Every shape is drawn at 20 px/mm, its narrow joints are thickened so no neck is thinner
than about 1.6 mm, and it is extruded to a flat 3.2 mm piece (prints flat, no support).
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

PX = 20
SIZE = 84.0                                   # canvas, mm


def canvas():
    n = int(SIZE * PX)
    im = Image.new("L", (n, n), 0)
    return im, ImageDraw.Draw(im)


def to_px(pts):
    return [((x + SIZE / 2) * PX, (SIZE / 2 - y) * PX) for x, y in pts]


def koch(n=3, R=34.0):
    tri = np.array([[R * np.cos(a), R * np.sin(a)] for a in np.radians([90, 210, 330])])
    pts = tri
    for _ in range(n):
        out = []
        for a, b in zip(pts, np.roll(pts, -1, axis=0)):
            d = (b - a) / 3
            peak = a + d + np.array([d[0] * 0.5 + d[1] * np.sqrt(3) / 2, -d[0] * np.sqrt(3) / 2 + d[1] * 0.5])
            out += [a, a + d, peak, a + 2 * d]
        pts = np.array(out)
    im, dr = canvas(); dr.polygon(to_px(pts), fill=255)
    return np.asarray(im) > 0, (0.0, R)                     # mask, loop anchor (top point)


def sierpinski(levels=4, side=64.0):
    h = side * np.sqrt(3) / 2
    top = np.array([0, h * 2 / 3 + 3])
    a, b, c = top, top + [-side / 2, -h], top + [side / 2, -h]
    im, dr = canvas()
    def tri(p, q, r, k):
        if k == 0:
            dr.polygon(to_px([p, q, r]), fill=255); return
        pq, qr, rp = (p + q) / 2, (q + r) / 2, (r + p) / 2
        tri(p, pq, rp, k - 1); tri(pq, q, qr, k - 1); tri(rp, qr, r, k - 1)
    tri(a, b, c, levels)
    base = b[1]
    dr.rectangle(to_px([(-4.5, base + 0.5), (4.5, base - 9)]), fill=255)      # trunk
    return np.asarray(im) > 0, tuple(a)


def pythagoras(depth=6, s=13.0, angle=np.radians(45)):
    im, dr = canvas()
    def square(p, v, k):
        # p: bottom-left corner, v: bottom edge vector
        w = np.array([-v[1], v[0]])
        q = [p, p + v, p + v + w, p + w]
        dr.polygon(to_px(q), fill=255)
        if k == 0:
            return
        c, sn = np.cos(angle), np.sin(angle)
        L = np.linalg.norm(v)
        u, wn = v / L, w / L
        left = L * c
        apex = p + w + u * left * c + wn * left * sn
        v1 = apex - (p + w)
        square(p + w, v1, k - 1)
        square(apex, (p + v + w) - apex, k - 1)
    square(np.array([-s / 2, -38.0]), np.array([s, 0.0]), depth)
    m = np.asarray(im) > 0
    ys = np.nonzero(m.any(1))[0]
    top_y = SIZE / 2 - ys.min() / PX
    return m, (0.0, top_y)


def pentaflake(levels=3, R=36.0):
    """Six pentagons per step, the outer five scaled by 1/(1 + phi): a five-pointed fractal star."""
    phi = (1 + 5 ** 0.5) / 2
    k = 1 / (1 + phi)
    im, dr = canvas()
    def flake(cx, cy, r, n, rot):
        if n == 0:
            pts = [(cx + r * np.cos(rot + np.pi / 2 + 2 * np.pi * i / 5), cy + r * np.sin(rot + np.pi / 2 + 2 * np.pi * i / 5)) for i in range(5)]
            dr.polygon(to_px(pts), fill=255); return
        r2 = r * k
        flake(cx, cy, r2, n - 1, rot + np.pi)
        for i in range(5):
            a = rot + np.pi / 2 + 2 * np.pi * i / 5
            d = r - r2
            flake(cx + d * np.cos(a), cy + d * np.sin(a), r2, n - 1, rot)
    flake(0, 0, R, levels, 0.0)
    m = np.asarray(im) > 0
    ys = np.nonzero(m.any(1))[0]
    return m, (0.0, SIZE / 2 - ys.min() / PX)


def finish(mask, anchor, neck=0.8, loop_r=4.2, hole_r=2.0):
    """Thicken necks (closing by a small disc, then a small dilation) and add the hanging loop."""
    r = int(neck * PX)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disc = xx ** 2 + yy ** 2 <= r * r
    m = ndi.binary_dilation(mask, structure=disc)
    m = ndi.binary_closing(m, structure=disc)
    im = Image.fromarray((m * 255).astype(np.uint8)); dr = ImageDraw.Draw(im)
    ax, ay = anchor
    cy = ay + loop_r + 0.5
    (x0, y0), (x1, y1) = to_px([(ax - 1.6, cy), (ax + 1.6, ay - 3.0)])
    dr.rectangle([x0, y0, x1, y1], fill=255)                       # stem into the shape
    (x0, y0), (x1, y1) = to_px([(ax - loop_r, cy + loop_r), (ax + loop_r, cy - loop_r)])
    dr.ellipse([x0, y0, x1, y1], fill=255)
    (x0, y0), (x1, y1) = to_px([(ax - hole_r, cy + hole_r), (ax + hole_r, cy - hole_r)])
    dr.ellipse([x0, y0, x1, y1], fill=0)
    return np.asarray(im) > 0


SHAPES = {"koch": koch, "sierpinski": sierpinski, "pythagoras": pythagoras, "pentaflake": pentaflake}
MASKS = {}


NECK = {"koch": 0.8, "sierpinski": 0.8, "pythagoras": 0.5, "pentaflake": 0.35}


def mask(name):
    if name not in MASKS:
        MASKS[name] = finish(*SHAPES[name](), neck=NECK[name])
    return MASKS[name]


def koch_lines(R=34.0, stroke=1.1):
    """Iterations 0, 1 and 2 drawn as lines inside the n = 3 snowflake: the construction, raised."""
    im, dr = canvas()
    tri = np.array([[R * np.cos(a), R * np.sin(a)] for a in np.radians([90, 210, 330])])
    for n, scale in ((0, 0.55), (1, 0.72), (2, 0.86)):
        pts = tri * scale
        for _ in range(n):
            out = []
            for a, b in zip(pts, np.roll(pts, -1, axis=0)):
                d = (b - a) / 3
                peak = a + d + np.array([d[0] * 0.5 + d[1] * np.sqrt(3) / 2, -d[0] * np.sqrt(3) / 2 + d[1] * 0.5])
                out += [a, a + d, peak, a + 2 * d]
            pts = np.array(out)
        p = to_px(pts)
        dr.line(p + [p[0]], fill=255, width=int(stroke * PX), joint="curve")
    return np.asarray(im) > 0


def height(name, plate=2.4, rim=1.2):
    """Heights in mm on the 20 px/mm grid: the plate, plus raised detail where the design has it."""
    m = mask(name)
    h = np.where(m, plate, 0.0)
    if name == "koch":
        h = np.where(koch_lines() & m, plate + rim, h)
    else:
        # a raised rim round every edge makes the fractal outline catch the light
        inner = ndi.binary_erosion(m, iterations=int(1.0 * PX))
        h = np.where(m & ~inner, plate + rim, h)
    return h


def thinnest(m):
    t = ndi.distance_transform_edt(m) / PX
    ridge = (t == ndi.maximum_filter(t, 3)) & m & (t > 0.05)
    return 2 * np.percentile(t[ridge], 1)


if __name__ == "__main__":
    tiles = []
    for name in SHAPES:
        m = mask(name)
        ys, xs = np.nonzero(m)
        print(f"{name}: {(xs.max()-xs.min())/PX:.1f} x {(ys.max()-ys.min())/PX:.1f} mm, thinnest ~{thinnest(m):.2f} mm")
        tiles.append(Image.fromarray(np.where(m, 40, 235).astype(np.uint8)).resize((420, 420)))
    sheet = Image.new("L", (1680, 420), 235)
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 420, 0))
    sheet.save("ornaments-flat.png")
