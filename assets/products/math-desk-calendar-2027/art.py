import numpy as np, math
from PIL import Image, ImageDraw
S = 1100
NAVY = np.array([14, 26, 52], float); GOLD = np.array([201, 162, 74], float); CREAM = np.array([243, 236, 221], float)
def pal(t, stops):
    """t in [0,1] -> rgb through list of (pos, rgb)."""
    t = np.clip(t, 0, 1); pos = [p for p, _ in stops]; out = np.zeros(t.shape + (3,))
    for c in range(3): out[..., c] = np.interp(t, pos, [rgb[c] for _, rgb in stops])
    return out
ICE = [(0, (8, 16, 40)), (.25, (20, 60, 130)), (.5, (70, 150, 210)), (.75, (200, 230, 245)), (1, (255, 250, 235))]
EMBER = [(0, (14, 20, 44)), (.3, (90, 40, 90)), (.55, (200, 80, 70)), (.8, (235, 170, 80)), (1, (252, 240, 200))]
def img(a): return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
def density(xs, ys, extent, stops, gamma=.45, size=S):
    x0, x1, y0, y1 = extent
    h, _, _ = np.histogram2d(ys, xs, bins=size, range=[[y0, y1], [x0, x1]])
    h = np.log1p(h); h = (h / h.max()) ** gamma
    return img(pal(h[::-1], stops))
def julia():
    r = np.linspace(-1.55, 1.55, S); X, Y = np.meshgrid(r, r[::-1]); Z = X + 1j * Y; c = -0.8 + 0.156j
    n = np.zeros(Z.shape); alive = np.ones(Z.shape, bool); sm = np.zeros(Z.shape)
    for i in range(300):
        Z[alive] = Z[alive] ** 2 + c; esc = alive & (abs(Z) > 4); sm[esc] = i + 1 - np.log2(np.log(abs(Z[esc]))); alive &= ~esc
    t = np.where(alive, 0, (sm / 40) % 1)
    out = pal(np.sqrt(np.clip(sm / 60, 0, 1)), ICE); out[alive] = (8, 16, 40); return img(out)
def mandel():
    cx, cy, w = -0.743643, 0.131825, 0.0028
    r = np.linspace(-w, w, S); X, Y = np.meshgrid(r + cx, (r + cy)[::-1]); C = X + 1j * Y; Z = np.zeros_like(C)
    alive = np.ones(C.shape, bool); sm = np.zeros(C.shape); N = 1800
    for i in range(N):
        Z[alive] = Z[alive] ** 2 + C[alive]; esc = alive & (abs(Z) > 8)
        sm[esc] = i + 1 - np.log2(np.log(abs(Z[esc]))); alive &= ~esc
    u = np.log1p(sm) * 1.15; t = (u % 1.0)
    CYC = [(0, (10, 18, 48)), (.25, (30, 80, 160)), (.5, (235, 228, 205)), (.75, (222, 168, 80)), (1, (10, 18, 48))]
    out = pal(t, CYC); out[alive] = (6, 10, 28); return img(out)
def newton():
    r = np.linspace(-1.6, 1.6, S); X, Y = np.meshgrid(r, r[::-1]); Z = X + 1j * Y
    roots = np.exp(2j * np.pi * np.arange(5) / 5); iters = np.zeros(Z.shape)
    for i in range(40):
        Z = Z - (Z ** 5 - 1) / (5 * Z ** 4 + 1e-12); iters += (abs(Z ** 5 - 1) > 1e-6)
    idx = np.argmin(abs(Z[..., None] - roots), axis=-1)
    cols = np.array([(40, 90, 170), (201, 162, 74), (170, 60, 90), (60, 150, 130), (232, 226, 205)], float)
    sh = 1 - np.clip(iters / 22, 0, 1) ** .8 * .75
    return img(cols[idx] * sh[..., None] + NAVY * (1 - sh[..., None]) * .3)
def lorenz():
    s, r, b, dt = 10., 28., 8 / 3, .004; p = np.array([1., 1., 1.]); pts = np.empty((260000, 3))
    f = lambda v: np.array([s * (v[1] - v[0]), v[0] * (r - v[2]) - v[1], v[0] * v[1] - b * v[2]])
    for i in range(pts.shape[0]):
        k1 = f(p); k2 = f(p + dt / 2 * k1); k3 = f(p + dt / 2 * k2); k4 = f(p + dt * k3); p = p + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4); pts[i] = p
    return density(pts[2000:, 0], pts[2000:, 2], (-26, 26, -2, 54), EMBER, .5)
def clifford():
    a, b, c, d = -1.4, 1.6, 1.0, 0.7; n = 3_000_000; x = np.empty(n); y = np.empty(n); x[0] = y[0] = .1
    for i in range(1, n): x[i] = math.sin(a * y[i - 1]) + c * math.cos(a * x[i - 1]); y[i] = math.sin(b * x[i - 1]) + d * math.cos(b * y[i - 1])
    return density(x, y, (-3.05, 3.05, -3.05, 3.05), ICE, .4)
def fern():
    rng = np.random.default_rng(3); n = 700000; x = np.empty(n); y = np.empty(n); x[0] = y[0] = 0; ch = rng.random(n)
    for i in range(1, n):
        px, py = x[i - 1], y[i - 1]; u = ch[i]
        if u < .01: x[i], y[i] = 0, .16 * py
        elif u < .86: x[i], y[i] = .85 * px + .04 * py, -.04 * px + .85 * py + 1.6
        elif u < .93: x[i], y[i] = .2 * px - .26 * py, .23 * px + .22 * py + 1.6
        else: x[i], y[i] = -.15 * px + .28 * py, .26 * px + .24 * py + .44
    return density(x, y, (-3.2, 3.2, -.4, 10.4 - 1.2), [(0, (8, 20, 36)), (.35, (20, 90, 70)), (.7, (110, 190, 120)), (1, (235, 245, 200))], .5)
def phyllo():
    im = Image.new('RGB', (S, S), tuple(NAVY.astype(int))); d = ImageDraw.Draw(im); N = 2600; ga = math.pi * (3 - math.sqrt(5))
    for n in range(1, N):
        r = 17.2 * math.sqrt(n); th = n * ga; x = S / 2 + r * math.cos(th); y = S / 2 + r * math.sin(th); t = n / N
        col = tuple(pal(np.array([t]), [(0, (230, 190, 90)), (.5, (240, 150, 110)), (1, (150, 120, 220))])[0].astype(int)); rr = 2 + 7 * t ** .8
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col)
    return im
def supersample(draw_fn, k=2):
    im = Image.new('RGB', (S * k, S * k), tuple(NAVY.astype(int))); draw_fn(ImageDraw.Draw(im), k); return im.resize((S, S), Image.LANCZOS)
def cardioid():
    def f(d, k):
        N = 360; R = S * k * .43; c = S * k / 2
        pt = lambda i: (c + R * math.cos(2 * math.pi * i / N - math.pi / 2), c + R * math.sin(2 * math.pi * i / N - math.pi / 2))
        d.ellipse([c - R, c - R, c + R, c + R], outline=(70, 90, 140), width=2 * k)
        for i in range(N):
            t = i / N; col = tuple(pal(np.array([t]), [(0, (201, 162, 74)), (.5, (235, 130, 110)), (1, (110, 150, 230))])[0].astype(int))
            d.line([pt(i), pt((2 * i) % N)], fill=col, width=k)
    return supersample(f)
def harmono():
    def f(d, k):
        t = np.linspace(0, 120, 90000); fr = (2.0, 3.01, 3.0, 2.0); ph = (0, math.pi / 2, math.pi / 3, 0); dm = (.0042, .0035, .0038, .0045)
        x = np.sin(fr[0] * t + ph[0]) * np.exp(-dm[0] * t) + np.sin(fr[1] * t + ph[1]) * np.exp(-dm[1] * t)
        y = np.sin(fr[2] * t + ph[2]) * np.exp(-dm[2] * t) + np.sin(fr[3] * t + ph[3]) * np.exp(-dm[3] * t)
        X = S * k / 2 + x * S * k * .235; Y = S * k / 2 + y * S * k * .235; m = len(t)
        for i in range(0, m - 1, 40):
            seg = list(zip(X[i:i + 42], Y[i:i + 42])); tt = i / m
            col = tuple(pal(np.array([tt]), [(0, (240, 215, 140)), (.6, (210, 150, 90)), (1, (120, 100, 160))])[0].astype(int)); d.line(seg, fill=col, width=max(1, k))
    return supersample(f)
def dragon():
    pts = [0j, 1 + 0j]
    for _ in range(13):
        piv = pts[-1]; pts = pts + [piv + (p - piv) * 1j for p in reversed(pts[:-1])]
    z = np.array(pts); z = z - (z.min().real + z.max().real) / 2 - 1j * ((z.imag.min() + z.imag.max()) / 2)
    sc = S * .88 / max(np.ptp(z.real), np.ptp(z.imag))
    def f(d, k):
        X = S * k / 2 + z.real * sc * k; Y = S * k / 2 + z.imag * sc * k; n = len(z)
        for i in range(0, n - 1, 16):
            t = i / n; col = tuple(pal(np.array([t]), [(0, (240, 200, 110)), (.5, (225, 120, 110)), (1, (120, 150, 230))])[0].astype(int))
            d.line(list(zip(X[i:i + 17], Y[i:i + 17])), fill=col, width=3 * k)
    return supersample(f)
def tree():
    def f(d, k):
        def br(x, y, ang, ln, depth):
            if depth == 0: return
            x2 = x + ln * math.cos(ang); y2 = y - ln * math.sin(ang); t = 1 - depth / 11
            col = tuple(pal(np.array([t]), [(0, (150, 110, 70)), (.6, (210, 170, 90)), (1, (180, 235, 170))])[0].astype(int))
            d.line([(x, y), (x2, y2)], fill=col, width=max(1, int(depth * 1.3 * k / 1.5)))
            br(x2, y2, ang + .46, ln * .74, depth - 1); br(x2, y2, ang - .46, ln * .74, depth - 1)
        br(S * k / 2, S * k * .97, math.pi / 2, S * k * .215, 11)
    return supersample(f)
def apollo():
    def f(d, k):
        c = S * k / 2; R = S * k * .46
        def circ(z, r, col, w): d.ellipse([c + (z.real - r) * R, c + (z.imag - r) * R, c + (z.real + r) * R, c + (z.imag + r) * R], outline=col, width=w)
        k0 = [-1, 2, 2, 3]; z0 = [0j, 0.5 + 0j, -0.5 + 0j, 2j / 3 - 0j * 0]
        z0 = [0j, .5 + 0j, -.5 + 0j, 0 + (2 / 3) * 1j]
        circ(0j, 1, (210, 180, 110), 2 * k)
        seen = []
        def rec(ka, za, kb, zb, kc, zc, kd, zd, depth):
            ke = 2 * (ka + kb + kc) - kd; ze = (2 * (ka * za + kb * zb + kc * zc) - kd * zd) / ke
            if ke > 500 or depth > 14: return
            t = min(1, math.log(ke) / math.log(500)); col = tuple(pal(np.array([t]), [(0, (230, 190, 100)), (.5, (225, 120, 110)), (1, (110, 150, 230))])[0].astype(int))
            circ(ze, 1 / ke, col, max(1, int(k * (2.2 - 1.6 * t)))); 
            rec(ka, za, kb, zb, ke, ze, kc, zc, depth + 1); rec(ka, za, kc, zc, ke, ze, kb, zb, depth + 1); rec(kb, zb, kc, zc, ke, ze, ka, za, depth + 1)
        for kk, zz in zip(k0[1:], z0[1:]): circ(zz, 1 / kk, (230, 200, 120), 2 * k)
        a, b, c3, dd = (k0[0], z0[0]), (k0[1], z0[1]), (k0[2], z0[2]), (k0[3], z0[3])
        rec(*b, *c3, *dd, *a, 0); rec(*a, *b, *dd, *c3, 0); rec(*a, *c3, *dd, *b, 0); rec(*a, *b, *c3, *dd, 0)
        # the fourth circle of the first quadruple: mirrored one
        ke = 2 * (k0[0] + k0[1] + k0[2]) - k0[3]
    return supersample(f)
ART = [julia, cardioid, fern, phyllo, lorenz, harmono, mandel, newton, dragon, clifford, tree, apollo]
if __name__ == '__main__':
    import sys, time
    from pathlib import Path
    out = Path('art'); out.mkdir(exist_ok=True)
    for i, fn in enumerate(ART, 1):
        t = time.time(); im = fn(); im.save(out / f'{i:02d}_{fn.__name__}.png'); print(i, fn.__name__, round(time.time() - t, 1), 's', flush=True)
