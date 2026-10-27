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


# --- Third series: more reliefs -------------------------------------------------------
# 11. Vogel's sunflower: seed n at angle n * 137.508 degrees and radius c * sqrt(n).
def _sunflower_field(X, Y, R=45.0, N=233):
    from scipy.spatial import cKDTree
    n = np.arange(1, N + 1)
    c = (R - 3.0) / np.sqrt(N)
    t = n * GOLDEN
    seeds = np.c_[c * np.sqrt(n) * np.cos(t), c * np.sqrt(n) * np.sin(t)]
    pts = np.c_[X.ravel(), Y.ravel()]
    d, i = cKDTree(seeds).query(pts)
    r = np.hypot(X, Y).ravel()
    dome = 5.0 + 13.0 * np.clip(1 - (r / R) ** 2, 0, 1)            # the head bulges toward the centre
    cap = np.sqrt(np.clip((0.62 * c) ** 2 - d ** 2, 0, None))      # one rounded seed per Voronoi cell
    return (dome + 1.6 * cap / (0.62 * c) * 2.2).reshape(X.shape)


def sunflower_relief(p):
    return _relief(p, "sunflower", lambda X, Y: _smooth(_sunflower_field(X, Y), 0.2), 92.0, 92.0, round_disc=True)


# 12. Koch snowflake ziggurat: iteration 4 at the base up to the triangle on top. Each level
#     contains the one above, so every wall is vertical and nothing overhangs.
def _koch(points, n):
    for _ in range(n):
        out = []
        for a, b in zip(points, np.roll(points, -1, axis=0)):
            d = (b - a) / 3
            peak = a + d + np.array([d[0] * 0.5 + d[1] * np.sqrt(3) / 2, -d[0] * np.sqrt(3) / 2 + d[1] * 0.5])  # outward for a CCW outline
            out += [a, a + d, peak, a + 2 * d]
        points = np.array(out)
    return points


def _koch_field(X, Y, side=78.0, levels=5, step=4.5, base=3.0):
    from matplotlib.path import Path as MPath
    R = side / np.sqrt(3)
    tri = np.array([[R * np.cos(a), R * np.sin(a)] for a in np.radians([90, 210, 330])])
    pts = np.c_[X.ravel(), Y.ravel()]
    h = np.zeros(len(pts))
    for k in range(levels):                       # level k is iteration (levels-1-k): wider at the bottom
        poly = _koch(tri, levels - 1 - k)
        inside = MPath(poly).contains_points(pts)
        h = np.where(inside, base + step * (k + 1), h)
    return h.reshape(X.shape)


def koch_ziggurat(p):
    return _relief(p, "koch", _koch_field, 92.0, 92.0, round_disc=True)


# 13. Gaussian primes: a pillar on every a + bi that is prime in Z[i], taller toward the centre.
def _gaussian_field(X, Y, R=45.0, unit=3.5, w=2.7):
    def is_prime(n):
        return n > 1 and all(n % q for q in range(2, int(n ** 0.5) + 1))
    m = int(R / unit)
    h = np.full(X.shape, 4.0)
    for a in range(-m, m + 1):
        for b in range(-m, m + 1):
            if a * a + b * b > (R / unit - 0.8) ** 2:
                continue
            if a and b:
                prime = is_prime(a * a + b * b)
            else:
                k = abs(a or b)
                prime = is_prime(k) and k % 4 == 3
            if prime:
                tall = 4.0 + 18.0 * (1 - np.hypot(a, b) * unit / R) ** 0.8
                sq = (np.abs(X - a * unit) <= w / 2) & (np.abs(Y - b * unit) <= w / 2)
                h = np.where(sq, np.maximum(h, tall), h)
    return h


def gaussian_primes(p):
    return _relief(p, "gauss", _gaussian_field, 92.0, 92.0, round_disc=True)


DESIGNS.update({
    "sunflower_relief": (sunflower_relief, (-47, 47, -47, 47, 0, 24), "Vogel's sunflower"),
    "koch_ziggurat": (koch_ziggurat, (-47, 47, -47, 47, 0, 26), "Koch snowflake ziggurat"),
    "gaussian_primes": (gaussian_primes, (-47, 47, -47, 47, 0, 24), "Gaussian primes"),
})


# --- Classic 3D graphs z = f(x, y) on a square tile ------------------------------------
def _graph(f, span, base=4.0, top=26.0, w=90.0):
    """Height field of f over [-span, span]^2, scaled to [base, top] mm."""
    def build(X, Y):
        u, v = X / (w / 2) * span, Y / (w / 2) * span
        z = f(u, v)
        z = (z - z.min()) / (z.max() - z.min())
        return _smooth(base + (top - base) * z, 0.3)
    return build


def _sinc(u, v):
    r = np.hypot(u, v) + 1e-9
    return np.sin(r) / r


def _peaks(x, y):
    return (3 * (1 - x) ** 2 * np.exp(-x ** 2 - (y + 1) ** 2) - 10 * (x / 5 - x ** 3 - y ** 5) * np.exp(-x ** 2 - y ** 2)
            - np.exp(-(x + 1) ** 2 - y ** 2) / 3)


def _two_waves(u, v, d=2.2, k=2.2):
    return np.cos(k * np.hypot(u - d, v)) + np.cos(k * np.hypot(u + d, v))


GRAPHS = {
    "graph_sinc": (_sinc, 12.0, "z = sin(r)/r"),
    "graph_saddle": (lambda u, v: u ** 2 - v ** 2, 1.0, "z = x² − y²"),
    "graph_monkey": (lambda u, v: u ** 3 - 3 * u * v ** 2, 1.0, "z = x³ − 3xy²"),
    "graph_waves": (_two_waves, 7.0, "z = cos(k r₁) + cos(k r₂)"),
    "graph_peaks": (_peaks, 3.0, "MATLAB peaks"),
    "graph_eggcrate": (lambda u, v: np.sin(u) * np.sin(v), 2.5 * np.pi, "z = sin x · sin y"),
}
for _name, (_f, _span, _label) in GRAPHS.items():
    DESIGNS[_name] = ((lambda name, f, span: (lambda p: _relief(p, name, _graph(f, span), 90.0, 90.0)))(_name, _f, _span),
                      (-46, 46, -46, 46, 0, 27), _label)


# --- Parametric curves as standing ribbons: a 3 mm wall along (x(t), y(t)), height h(t). ---
# Walls are vertical, so they never need support; where the curve crosses itself the taller wins.
def _ribbon_field(curve, w=92.0, wall=3.2, base=3.0, hmin=8.0, hmax=34.0, n=20000):
    def build(X, Y):
        from scipy.spatial import cKDTree
        t = np.linspace(0, 1, n, endpoint=False)
        x, y, s = curve(t)                       # s in [0, 1] drives the height
        x = x / np.abs(x).max() * (w / 2 - 6); y = y / np.abs(y).max() * (w / 2 - 6)
        tree = cKDTree(np.c_[x, y])
        pts = np.c_[X.ravel(), Y.ravel()]
        hits = tree.query_ball_point(pts, wall / 2)
        h = np.zeros(len(pts))
        hs = hmin + (hmax - hmin) * s
        for i, idx in enumerate(hits):
            if idx:
                h[i] = hs[idx].max()
        plate = np.hypot(X, Y).ravel() <= w / 2 - 1          # a thin disc ties every loop together
        return np.where(plate, np.maximum(h, base), 0).reshape(X.shape)
    return build


def _lissajous(t):
    a = 2 * np.pi * t
    return np.sin(3 * a + np.pi / 2), np.sin(2 * a), 0.5 + 0.5 * np.cos(2 * a)


def _spirograph(t, R=5.0, r=3.0, d=5.0):
    a = 2 * np.pi * 3 * t                        # three turns close the curve
    x = (R - r) * np.cos(a) + d * np.cos((R - r) / r * a)
    y = (R - r) * np.sin(a) - d * np.sin((R - r) / r * a)
    rho = np.hypot(x, y)
    return x, y, rho / rho.max()                 # taller at the tips of the petals


def _butterfly(t):
    a = 12 * np.pi * t
    r = np.exp(np.sin(a)) - 2 * np.cos(4 * a) + np.sin((2 * a - np.pi) / 24) ** 5
    x, y = r * np.sin(a), r * np.cos(a)
    return x, y, np.clip(np.hypot(x, y) / 4.5, 0, 1)


for _name, _curve, _label in [("ribbon_lissajous", _lissajous, "Lissajous ribbon"),
                              ("ribbon_spirograph", _spirograph, "Spirograph ribbon"),
                              ("ribbon_butterfly", _butterfly, "Butterfly curve ribbon")]:
    DESIGNS[_name] = ((lambda name, c: (lambda p: _relief(p, name, _ribbon_field(c), 92.0, 92.0, round_disc=True)))(_name, _curve),
                      (-47, 47, -47, 47, 0, 35), _label)


# Trefoil knot as a tube (needs support; shown for comparison).
def trefoil(p, scale=13.0, r=4.5):
    from scipy.spatial import cKDTree
    t = np.linspace(0, 2 * np.pi, 4000, endpoint=False)
    c = np.c_[np.sin(t) + 2 * np.sin(2 * t), np.cos(t) - 2 * np.cos(2 * t), -np.sin(3 * t)] * scale
    c[:, 2] += scale + r
    d, _ = cKDTree(c).query(p)
    return d - r


DESIGNS["trefoil"] = (trefoil, (-45, 45, -45, 45, 0, 36), "Trefoil knot")


# --- Fourth series ----------------------------------------------------------------------
# 14. Gabriel's horn: y = 1/x for 1 <= x <= 8 turned about its axis, standing on its bell.
#     The radius only shrinks going up, so every surface faces up. Volume pi, area infinite.
def gabriel(p, R=40.0, k=13.5, xmax=8.0):
    rho, _, z = cyl(p)
    x = 1 + z / k
    r = R / np.clip(x, 1, None)
    d = (rho - r) / np.sqrt(1 + (R / (k * np.clip(x, 1, None) ** 2)) ** 2)   # distance to a sloped wall
    return np.maximum(d, slab(z, 0, (xmax - 1) * k))


# 15. Julia set z -> z^2 + c with Douady's rabbit, c = -0.123 + 0.745i, as escape-time relief.
def _julia_field(X, Y, w=112.0, d=84.0, it=200, c=-0.123 + 0.745j):
    z = (X / (w / 2) * 1.62) + 1j * (Y / (d / 2) * 1.215)
    n = np.zeros(z.shape); alive = np.ones(z.shape, bool)
    for i in range(it):
        z[alive] = z[alive] ** 2 + c
        esc = alive & (np.abs(z) > 4)
        n[esc] = i + 1 - np.log2(np.log2(np.abs(z[esc])))
        alive &= ~esc
    n[alive] = it
    h = 4.0 + 24.0 * np.sqrt(np.clip(n, 0, 60) / 60)
    from scipy.ndimage import grey_opening
    r = int(1.5 / 0.25); yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return _smooth(grey_opening(h, footprint=(xx ** 2 + yy ** 2) <= r * r), 0.35)


def julia_relief(p):
    return _relief(p, "julia", _julia_field, 112.0, 84.0)


# 16. Hilbert curve of order 4: one line through all 256 cells of the square, rising as it goes.
def _hilbert(order):
    n = 2 ** order
    pts = []
    for d in range(n * n):
        x = y = 0; t = d; s = 1
        while s < n:
            rx = 1 & (t // 2); ry = 1 & (t ^ rx)
            if ry == 0:
                if rx == 1:
                    x, y = s - 1 - x, s - 1 - y
                x, y = y, x
            x += s * rx; y += s * ry; t //= 4; s *= 2
        pts.append((x, y))
    return np.array(pts, float), n


def _hilbert_curve(t, order=4):
    pts, n = _hilbert(order)
    seg = np.linspace(0, len(pts) - 1, len(t))
    i = np.clip(seg.astype(int), 0, len(pts) - 2); f = seg - i
    xy = pts[i] * (1 - f[:, None]) + pts[i + 1] * f[:, None]
    xy = (xy - (n - 1) / 2) / ((n - 1) / 2)
    return xy[:, 0], xy[:, 1], t


def _square_ribbon_field(curve, w=96.0, wall=3.2, base=3.0, hmin=7.0, hmax=30.0, n=40000):
    def build(X, Y):
        from scipy.spatial import cKDTree
        t = np.linspace(0, 1, n)
        x, y, s = curve(t)
        x = x * (w / 2 - 4); y = y * (w / 2 - 4)
        hits = cKDTree(np.c_[x, y]).query_ball_point(np.c_[X.ravel(), Y.ravel()], wall / 2)
        hs = hmin + (hmax - hmin) * s
        h = np.array([hs[i].max() if i else base for i in hits])
        return h.reshape(X.shape)
    return build


def hilbert_ribbon(p):
    return _relief(p, "hilbert", _square_ribbon_field(_hilbert_curve), 100.0, 100.0)


DESIGNS.update({
    "gabriel": (gabriel, (-41, 41, -41, 41, 0, 95), "Gabriel's horn"),
    "julia_relief": (julia_relief, (-57, 57, -43, 43, 0, 29), "Julia set, Douady's rabbit"),
    "hilbert_ribbon": (hilbert_ribbon, (-51, 51, -51, 51, 0, 31), "Hilbert curve"),
})


# Gabriel's horn as two pieces: the horn (with a 3 mm upright lip so the bell has no knife edge)
# and a matte plinth with a pocket for it, the name and equations engraved round the top,
# and the volume and area integrals underneath.
def gabriel_horn(p, R=39.0, k=13.5, xmax=8.0, lip=3.0):
    rho, _, z = cyl(p)
    horn = gabriel(p - np.array([0, 0, lip]), R=R, k=k, xmax=xmax)
    foot = np.maximum(rho - R, slab(z, 0, lip + 0.5))
    return np.minimum(horn, foot)


def gabriel_plinth(p, R=52.0, H=7.0, pocket=39.0, clearance=0.25, depth=2.5, cut=0.6):
    from engrave_horn import TOP, UNDER, sample
    rho, _, z = cyl(p)
    disc = np.maximum(rho - R, slab(z, 0, H))
    hole = np.maximum(rho - (pocket + clearance), slab(z, H - depth, H + 1))
    d = np.maximum(disc, -hole)
    top = np.maximum(sample(TOP, p[:, 0], p[:, 1]), slab(z, H - cut, H + 1))
    # An engraving underneath made Slant 3D ask for support (its letter ceilings), so only the top ring is cut.
    return np.maximum(d, -top)


def gabriel_duo(p):
    return np.minimum(gabriel_plinth(p), gabriel_horn(p - np.array([0, 0, 4.5])))


DESIGNS.update({
    "gabriel_horn": (gabriel_horn, (-40, 40, -40, 40, 0, 98), "Gabriel's horn"),
    "gabriel_plinth": (gabriel_plinth, (-53, 53, -53, 53, 0, 7), "Gabriel's horn plinth"),
    "gabriel_duo": (gabriel_duo, (-53, 53, -53, 53, 0, 103), "Gabriel's horn on its plinth"),
})


# The horn with a tunnel: open at the base, it climbs inside the horn and narrows to a point.
# Built from the tip down, its radius may grow by at most tan(28 deg) per mm (so its ceiling never
# leans past Slant 3D's limit) and always keeps 3 mm of wall to the outside.
def _bore_profile(R=39.0, k=13.5, lip=3.0, wall=3.8, lean=28.0, z_top=92.0, dz=0.05):
    zs = np.arange(0, z_top + dz, dz)
    x = 1 + np.clip(zs - lip, 0, None) / k
    outer = np.where(zs < lip + 0.5, R, R / x)
    rb = np.zeros_like(zs)
    grow = np.tan(np.radians(lean)) * dz
    for i in range(len(zs) - 2, -1, -1):
        rb[i] = min(outer[i] - wall, rb[i + 1] + grow)
    return zs, np.clip(rb, 0, None)


_BORE = _bore_profile()


def gabriel_horn_hollow(p):
    zs, rb = _BORE
    rho, _, z = cyl(p)
    r = np.interp(z, zs, rb, right=0.0)
    slope = np.gradient(rb, zs)
    s = np.interp(z, zs, slope, right=0.0)
    bore = (rho - r) / np.sqrt(1 + s * s)
    bore = np.where(z > zs[-1], 1e3, bore)
    return np.maximum(gabriel_horn(p), -np.maximum(bore, -z - 1.0))


DESIGNS["gabriel_horn_hollow"] = (gabriel_horn_hollow, (-40, 40, -40, 40, 0, 98), "Gabriel's horn with its tunnel")
