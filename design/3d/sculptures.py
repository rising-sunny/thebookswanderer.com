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
