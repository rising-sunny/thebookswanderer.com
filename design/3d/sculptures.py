"""Support-free mathematical sculptures as signed distance fields.

Each design is printable on its flat base with walls and rods kept steeper than
45 degrees, so it needs no support. sdf(p) takes an (N, 3) array in mm.
"""
import numpy as np

TAU = 2 * np.pi


def capsule(p, a, b, r):
    pa, ba = p - a, b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0, 1)
    return np.linalg.norm(pa - h[:, None] * ba, axis=1) - r


def cyl(p):
    return np.hypot(p[:, 0], p[:, 1]), np.arctan2(p[:, 1], p[:, 0]), p[:, 2]


def slab(z, z0, z1):
    return np.maximum(z0 - z, z - z1)


# 1. Hyperboloid of one sheet: straight rods that make a curved waist.
def hyperboloid(p, R=32.0, H=96.0, n=18, twist=TAU / 3, r=1.8, top_ring=False):
    d = np.full(len(p), 1e9)
    for s in (1, -1):
        for i in range(n):
            t0 = TAU * i / n
            a = np.array([R * np.cos(t0), R * np.sin(t0), 3.0])
            b = np.array([R * np.cos(t0 + s * twist), R * np.sin(t0 + s * twist), H - 3.0])
            d = np.minimum(d, capsule(p, a, b, r))
    rho, _, z = cyl(p)
    ring = lambda z0, z1: np.maximum(np.abs(rho - R) - 3.0, slab(z, z0, z1))
    # the rods meet in pairs at the top, so the crown needs no ring (a flat ring would need support)
    return np.minimum(d, np.minimum(ring(0, 4.5), ring(H - 4.5, H)) if top_ring else ring(0, 4.5))


# 2. Fibonacci lattice: 13 and 21 spirals, the counts in a sunflower head.
def fibonacci(p, H=100.0, wall=1.8, rib=0.17):
    rho, th, z = cyl(p)
    u = z / H - 0.5
    R = 26 + 30 * u * u                     # an hourglass of revolution
    k = 0.026                               # radians per mm: ribs stay steeper than 45 degrees
    f1 = np.abs(np.sin(13 * (th - k * z) / 2)) - rib
    f2 = np.abs(np.sin(21 * (th + k * z) / 2)) - rib * 1.3
    ribs = np.minimum(f1, f2) * R / 6.5     # rough mm scale
    shell = np.abs(rho - R) - wall / 2
    lattice = np.maximum(shell, ribs)
    band = np.maximum(shell, np.minimum(slab(z, 0, 5), slab(z, H - 4, H)))
    base = np.maximum(rho - R + wall / 2 - 0.01 - 1e-9, slab(z, 0, 2.2))
    body = np.minimum(np.minimum(lattice, band), base)
    return np.maximum(body, slab(z, 0, H))


# 3. Gyroid in a cylinder, flat at both ends.
def gyroid(p, R=34.0, H=80.0, cell=16.0, wall=1.7):
    k = TAU / cell
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    g = np.sin(k * x) * np.cos(k * y) + np.sin(k * y) * np.cos(k * z) + np.sin(k * z) * np.cos(k * x)
    sheet = np.abs(g) / (k * 1.5) - wall / 2
    rho = np.hypot(x, y)
    skin = np.maximum(np.abs(rho - R + 1) - 1.0, np.minimum(slab(z, 0, 3), slab(z, H - 2, H)))
    return np.maximum(np.minimum(sheet, skin), np.maximum(rho - R, slab(z, 0, H)))


# 4. Twisted rose curve r = 1 + a cos(5 theta), turning as it rises.
def rose(p, H=110.0, wall=1.6):
    rho, th, z = cyl(p)
    u = np.clip(z / H, 0, 1)
    R = 24 + 10 * np.sin(np.pi * u) ** 1.2
    r = R * (1 + 0.16 * np.cos(5 * (th - 0.9 * np.pi * u)))
    shell = (np.abs(rho - r) - wall / 2) * 0.55
    base = np.maximum(rho - r, slab(z, 0, 2.4)) * 0.55
    return np.maximum(np.minimum(shell, base), slab(z, 0, H))


DESIGNS = {
    "hyperboloid": (hyperboloid, (-38, 38, -38, 38, 0, 96), "Hyperboloid of one sheet"),
    "fibonacci": (fibonacci, (-36, 36, -36, 36, 0, 100), "Fibonacci spiral lattice 13 / 21"),
    "gyroid": (gyroid, (-35, 35, -35, 35, 0, 80), "Gyroid column"),
    "rose": (rose, (-42, 42, -42, 42, 0, 110), "Twisted rose curve r = 1 + 0.16 cos 5θ"),
}


# Reinforced hyperboloid: thicker rods and a crown of arches joining the rod tips.
# The arches rise at 45 degrees from each tip, so the crown prints without support.
def _rods(p, R, H, n, twist, r):
    d = np.full(len(p), 1e9)
    for s in (1, -1):
        for i in range(n):
            t0 = TAU * i / n
            a = np.array([R * np.cos(t0), R * np.sin(t0), 3.0])
            b = np.array([R * np.cos(t0 + s * twist), R * np.sin(t0 + s * twist), H - 3.0])
            d = np.minimum(d, capsule(p, a, b, r))
    return d


def smin(a, b, k):
    """Smooth union: rounds the joint so stress does not gather in a sharp corner."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def crown(p, R, H, n, top=10.0, half=2.2):
    rho, th, z = cyl(p)
    step = TAU / n                                          # the rod tips sit every 360/n degrees
    s = R * np.abs((th + step / 2) % step - step / 2)       # arc distance to the nearest tip
    bottom = (H - 3.0) + s                                  # 45 degree arches between tips
    return np.maximum(np.maximum(np.abs(rho - R) - half, bottom - z), z - (H + top - 3.0))


def hyperboloid_strong(p, R=32.0, H=96.0, n=18, twist=TAU / 3, r=2.2, base=True):
    rho, _, z = cyl(p)
    d = smin(_rods(p, R, H, n, twist, r), crown(p, R, H, n), 1.2)
    ring = np.maximum(np.abs(rho - R) - 3.0, slab(z, 0, 4.5))
    if base:
        plate = np.maximum(rho - (R + 6), slab(z, 0, 3.0))    # a wider, solid foot for stability
        ring = np.minimum(ring, plate)
    return smin(d, ring, 1.5)


# Two-colour version: the lattice stands in a groove of a separate plinth.
def hyperboloid_lattice(p):
    return hyperboloid_strong(p, base=False)


def plinth(p, R=32.0, clearance=0.25, depth=0.6):
    rho, _, z = cyl(p)
    disc = np.maximum(rho - (R + 9), slab(z, 0, 7.0))
    groove = np.maximum(np.abs(rho - R) - (3.0 + clearance), slab(z, 4.0, 8.0))
    d = np.maximum(disc, -groove)
    if depth:                       # the equation, cut into the underside
        from engrave import text2d
        cut = np.maximum(text2d(p[:, 0], p[:, 1]), slab(z, -1.0, depth))
        d = np.maximum(d, -cut)
    return d


def hyperboloid_duo(p):
    """Both pieces assembled, only to check the stability of the pair."""
    return np.minimum(plinth(p), hyperboloid_lattice(p - np.array([0, 0, 4.0])))


DESIGNS.update({
    "hyperboloid_duo": (hyperboloid_duo, (-42, 42, -42, 42, 0, 110), "Two-colour pair, assembled"),
    "hyperboloid_strong": (hyperboloid_strong, (-39, 39, -39, 39, 0, 106), "Hyperboloid, reinforced"),
    "hyperboloid_lattice": (hyperboloid_lattice, (-36, 36, -36, 36, 0, 106), "Hyperboloid lattice (two-colour)"),
    "plinth": (plinth, (-42, 42, -42, 42, 0, 7), "Plinth (two-colour)"),
})


# --- Second series -----------------------------------------------------------------
PHI = (1 + 5 ** 0.5) / 2
GOLDEN = TAU * (2 - PHI)                # 137.508 degrees


def _diagonal_up(p, center):
    """Coordinates of a cube standing on a corner: the body diagonal (1,1,1) points up."""
    u = np.array([1, -1, 0]) / 2 ** 0.5
    w = np.array([1, 1, 1]) / 3 ** 0.5
    v = np.cross(w, u)
    q = p - center
    return np.outer(q[:, 0], u) + np.outer(q[:, 1], v) + np.outer(q[:, 2], w)


def menger_sdf(q, level):
    """Menger sponge filling [-1, 1]^3 (distance in the same units)."""
    a = np.abs(q) - 1
    d = np.linalg.norm(np.maximum(a, 0), axis=1) + np.minimum(a.max(axis=1), 0)
    s = 1.0
    for _ in range(level):
        m = np.mod(q * s, 2.0) - 1.0
        s *= 3.0
        r = np.abs(1.0 - 3.0 * np.abs(m))
        da, db, dc = np.maximum(r[:, 0], r[:, 1]), np.maximum(r[:, 1], r[:, 2]), np.maximum(r[:, 2], r[:, 0])
        c = (np.minimum(np.minimum(da, db), dc) - 1.0) / s
        d = np.maximum(d, c)
    return d


# 4. Menger sponge on its corner: every face leans at 54.7 degrees, so no support.
def menger(p, side=72.0, level=3, socket=9.0):
    b = side / 2
    lift = socket                                       # the lowest corner sinks into the plinth
    q = _diagonal_up(p, np.array([0, 0, b * 3 ** 0.5 - lift + 6.0])) / b
    cube = menger_sdf(q, level) * b
    rho, _, z = cyl(p)
    plinth = np.maximum(rho - 40.0, slab(z, 0, 6.0))
    return np.minimum(cube, plinth)


# 5. Golden spiral: a wall on r = a * phi^(2 theta / pi) that rises toward its eye.
def golden_spiral(p, a=2.5, wall=3.4, rmax=44.0, hmin=10.0, hmax=92.0):
    rho, th, z = cyl(p)
    k = np.log(PHI) / (TAU / 4)
    turns = np.log(rmax / a) / k / TAU          # the spiral grows by phi every quarter turn
    d = np.full(len(p), 1e9)
    for m in range(-1, int(np.ceil(turns)) + 2):
        t = th + TAU * m
        r = a * np.exp(k * np.clip(t, 0, TAU * turns + np.pi))
        valid = (t >= 0) & (t <= TAU * turns)
        dist = np.abs(rho - r) / np.sqrt(1 + k * k) - wall / 2
        d = np.where(valid, np.minimum(d, dist), d)
    rr = np.clip(rho / rmax, 0, 1)
    top = hmin + (hmax - hmin) * (1 - rr) ** 1.3
    wallz = np.maximum(d, slab(z, 0, top))
    eye = np.maximum(rho - 3.4, slab(z, 0, hmax))
    base = np.maximum(rho - (rmax + 4), slab(z, 0, 3.0))
    return np.minimum(np.minimum(wallz, eye), base)


# 6. Golden-angle cone: 144 scales, each turned 137.5 degrees from the last.
_CONE_H, _CONE_R, _N = 104.0, 34.0, 144


def _cone_r(z):
    return _CONE_R * np.clip(1 - z / _CONE_H, 0, 1) ** 0.75


def _scales():
    zs = np.linspace(0, _CONE_H, 2000)
    area = np.cumsum(_cone_r(zs)); area /= area[-1]
    n = np.arange(_N)
    z = np.interp((n + 0.6) / (_N + 1) * 0.93, area, zs)
    t = n * GOLDEN
    r = _cone_r(z)
    return np.c_[r * np.cos(t), r * np.sin(t), z], t


def pinecone(p, size=7.2):
    from scipy.spatial import cKDTree
    centers, angles = _scales()
    rho, _, z = cyl(p)
    body = np.maximum(rho - _cone_r(z) + 1.0, slab(z, 0, _CONE_H))
    tree = cKDTree(centers)
    _, idx = tree.query(p, k=4)
    d = np.full(len(p), 1e9)
    for j in range(4):
        c = centers[idx[:, j]]; t = angles[idx[:, j]]
        er = np.c_[np.cos(t), np.sin(t), np.zeros(len(t))]
        q = p - c
        bump = np.linalg.norm((q - er * 0.5) * np.array([1, 1, 1.35]), axis=1) - size * (0.55 + 0.45 * _cone_r(c[:, 2]) / _CONE_R)
        under = ((q * er).sum(1) - q[:, 2] - 1.0) / 2 ** 0.5       # 45 degree underside
        d = np.minimum(d, np.maximum(bump, under))
    base = np.maximum(rho - (_CONE_R + 3), slab(z, 0, 3.0))
    return np.minimum(np.minimum(body, d), base)


DESIGNS.update({
    "menger": (menger, (-62, 62, -62, 62, 0, 132), "Menger sponge on its corner"),
    "golden_spiral": (golden_spiral, (-49, 49, -49, 49, 0, 94), "Golden spiral"),
    "pinecone": (pinecone, (-40, 40, -40, 40, 0, 106), "Golden-angle cone"),
})


# 7. |Gamma(z)| relief, after Jahnke and Emde's 1909 plot: every surface faces up, so it never
#    needs support. Poles at 0, -1, -2, ... rise as towers, cut flat at CLIP.
_GAMMA = {}


def _gamma_grid(w=112.0, d=76.0, step=0.25, clip=5.0, base=5.0, top=34.0, tower=2.2):
    """|Gamma| over x in [-4.3, 4.1], y in [-2.9, 2.9], as heights in mm on a fine grid.
    The towers are widened by a disc of radius `tower` so none is thinner than 4.4 mm."""
    if "h" not in _GAMMA:
        from scipy.special import gamma as G
        from scipy.ndimage import grey_dilation
        xs = np.arange(-w / 2, w / 2 + step, step); ys = np.arange(-d / 2, d / 2 + step, step)
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        zc = (-4.4 + (X + w / 2) / w * 7.6) + 1j * (Y / (d / 2) * 2.6)
        with np.errstate(all="ignore"):
            g = np.abs(G(zc))
        g = np.where(np.isfinite(g), g, clip)
        h = base + (top - base) * np.tanh(g / clip * 1.4)   # rounded summits instead of flat cuts
        r = int(tower / step)
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
        h = grey_dilation(h, footprint=(xx ** 2 + yy ** 2) <= r * r)
        _GAMMA.update(h=h.astype(np.float32), x0=xs[0], y0=ys[0], step=step)
    return _GAMMA


def gamma_relief(p, w=112.0, d=76.0):
    from scipy.ndimage import map_coordinates
    g = _gamma_grid(w, d)
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    h = map_coordinates(g["h"], [(x - g["x0"]) / g["step"], (y - g["y0"]) / g["step"]], order=1, mode="nearest")
    top = (z - h) * 0.3                                    # height field, kept Lipschitz for marching
    a = np.abs(np.c_[x, y]) - np.array([w / 2 - 4, d / 2 - 4])
    rect = np.linalg.norm(np.maximum(a, 0), axis=1) + np.minimum(a.max(axis=1), 0) - 4
    return np.maximum(np.maximum(top, rect), -z)


DESIGNS["gamma_relief"] = (gamma_relief, (-57, 57, -39, 39, 0, 35), "Gamma function relief")


# --- Reliefs: z = f(x, y) on a base. Every surface faces up, so none needs support. ---
_FIELDS = {}


def _relief(p, key, build, w, d, step=0.25, round_disc=False):
    """Signed distance to a height field on a w x d tile (or a disc of diameter w)."""
    from scipy.ndimage import map_coordinates
    if key not in _FIELDS:
        xs = np.arange(-w / 2, w / 2 + step, step); ys = np.arange(-d / 2, d / 2 + step, step)
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        _FIELDS[key] = (build(X, Y).astype(np.float32), xs[0], ys[0], step)
    h0, x0, y0, st = _FIELDS[key]
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    h = map_coordinates(h0, [(x - x0) / st, (y - y0) / st], order=1, mode="nearest")
    top = (z - h) * 0.3
    if round_disc:
        edge = np.hypot(x, y) - w / 2
    else:
        a = np.abs(np.c_[x, y]) - np.array([w / 2 - 4, d / 2 - 4])
        edge = np.linalg.norm(np.maximum(a, 0), axis=1) + np.minimum(a.max(axis=1), 0) - 4
    return np.maximum(np.maximum(top, edge), -z)


def _smooth(h, mm, step=0.25):
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(h, mm / step)


# 8. |zeta(s)| on the strip 0 < Re s < 1 and beyond: its zeros sit on Re s = 1/2 as dimples.
def _zeta_field(X, Y, w=76.0, d=112.0):
    import mpmath
    from scipy.ndimage import zoom
    c = 4                                            # evaluate on a 1 mm grid, then interpolate
    Xc, Yc = X[::c, ::c], Y[::c, ::c]
    sig = -0.6 + (Xc + w / 2) / w * 2.2                # Re s from -0.6 to 1.6
    t = 3.0 + (Yc + d / 2) / d * 38.0                  # Im s from 3 to 41: six zeros
    g = np.vectorize(lambda a, b: float(abs(mpmath.zeta(complex(a, b)))))(sig, t)
    g = zoom(g, (X.shape[0] / g.shape[0], X.shape[1] / g.shape[1]), order=3)[:X.shape[0], :X.shape[1]]
    return 4.0 + 22.0 * np.tanh(g / 2.2)


def zeta_relief(p):
    return _relief(p, "zeta", lambda X, Y: _smooth(_zeta_field(X, Y), 0.4), 76.0, 112.0)


# 9. Mandelbrot mountain: escape time as height; the set itself is the summit plateau.
def _mandel_field(X, Y, w=112.0, d=84.0, it=200):
    c = (-2.15 + (X + w / 2) / w * 2.9) + 1j * (Y / (d / 2) * 1.09)
    z = np.zeros_like(c); n = np.zeros(c.shape)
    alive = np.ones(c.shape, bool)
    for i in range(it):
        z[alive] = z[alive] ** 2 + c[alive]
        esc = alive & (np.abs(z) > 4)
        n[esc] = i + 1 - np.log2(np.log2(np.abs(z[esc])))
        alive &= ~esc
    n[alive] = it
    v = np.sqrt(np.clip(n, 0, 60) / 60)
    h = 4.0 + 24.0 * v
    # Opening by a 3 mm disc: crests and needles thinner than 3 mm are lowered until they are not.
    from scipy.ndimage import grey_opening
    r = int(1.5 / 0.25)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    h = grey_opening(h, footprint=(xx ** 2 + yy ** 2) <= r * r)
    return _smooth(h, 0.35)


def mandelbrot_relief(p, depth=0.6):
    d = _relief(p, "mandel", _mandel_field, 112.0, 84.0)
    if depth:                                    # the iteration and the set's definition, cut underneath
        from engrave_tile import text2d
        cut = np.maximum(text2d(p[:, 0], p[:, 1]), slab(p[:, 2], -1.0, depth))
        d = np.maximum(d, -cut)
    return d


# 10. A drum's vibration mode: J_4(j_{4,3} r) cos(4 theta), the shape a drumhead takes at one note.
def _drum_field(X, Y, R=45.0):
    from scipy.special import jv, jn_zeros
    r = np.hypot(X, Y) / R; th = np.arctan2(Y, X)
    k = jn_zeros(4, 3)[-1]
    f = jv(4, k * np.clip(r, 0, 1)) * np.cos(4 * th)
    f /= np.abs(f).max()
    return 9.0 + 7.0 * f


def drum_relief(p):
    return _relief(p, "drum", _drum_field, 90.0, 90.0, round_disc=True)


DESIGNS.update({
    "zeta_relief": (zeta_relief, (-39, 39, -57, 57, 0, 27), "Riemann zeta relief"),
    "mandelbrot_relief": (mandelbrot_relief, (-57, 57, -43, 43, 0, 29), "Mandelbrot mountain"),
    "drum_relief": (drum_relief, (-46, 46, -46, 46, 0, 17), "Drum mode J4"),
})
