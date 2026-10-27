"""Exact mesh of the tunnelled Gabriel's horn: its profile turned about the axis (no voxels)."""
import numpy as np
from sculptures import _BORE
from gyroid import save_stl

R, K, LIP, XMAX, N = 39.0, 13.5, 3.0, 8.0, 512


def profile():
    zt = LIP + (XMAX - 1) * K                                   # top of the horn
    zs, rb = _BORE
    end = np.nonzero(rb > 0.02)[0][-1]
    loop = [(rb[0], 0.0), (R, 0.0), (R, LIP + 0.5), (R / (1 + 0.5 / K), LIP + 0.5)]
    for z in np.linspace(LIP + 0.5, zt, 700)[1:]:
        loop.append((R / (1 + (z - LIP) / K), z))
    loop += [(0.0, zt), (0.0, zs[end + 1])]
    for i in range(end, 0, -4):
        loop.append((rb[i], zs[i]))
    return np.array(loop)


def lathe(loop, n=N):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    c, s = np.cos(a), np.sin(a)
    faces = []
    for (r0, z0), (r1, z1) in zip(loop, np.roll(loop, -1, axis=0)):
        p = np.c_[r0 * c, r0 * s, np.full(n, z0)]
        q = np.c_[r1 * c, r1 * s, np.full(n, z1)]
        pk, qk = np.roll(p, -1, axis=0), np.roll(q, -1, axis=0)
        if r0 > 0:
            faces.append(np.stack([p, pk, qk], 1))
        if r1 > 0:
            faces.append(np.stack([p, qk, q], 1))
    return np.concatenate(faces)


if __name__ == "__main__":
    tri = lathe(profile())
    v, inv = np.unique(tri.reshape(-1, 3).round(5), axis=0, return_inverse=True)
    save_stl("gabriel_horn_exact.stl", v, inv.reshape(-1, 3))
    print(len(tri), "triangles", v.min(0).round(1), v.max(0).round(1))
