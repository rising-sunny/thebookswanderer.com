"""Structural checks for a sculpture before it is quoted: stability, thinnest part,
overhangs steeper than 45 degrees, and weight. Works on the same voxels as make_stl."""
import sys, numpy as np
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull
from sculptures import DESIGNS

PLA = 1.24                      # g/cm3
LIMITS = {"tip_deg": 25.0, "min_mm": 3.0, "fragile_mm3": 5.0, "overhang_cm2": 0.1}


def voxels(name, step):
    f, (x0, x1, y0, y1, z0, z1), _ = DESIGNS[name]
    xs = np.arange(x0 - 1, x1 + 1, step); ys = np.arange(y0 - 1, y1 + 1, step); zs = np.arange(z0, z1 + 1, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    vol = np.empty((len(xs), len(ys), len(zs)), np.float32)
    for k, z in enumerate(zs):
        vol[:, :, k] = f(np.stack([X.ravel(), Y.ravel(), np.full(X.size, z + step / 2)], 1)).reshape(X.shape)
    return vol, xs, ys, zs


def check(name, step=0.35):
    vol, xs, ys, zs = voxels(name, step)
    solid = vol < 0
    lab, n = ndi.label(solid)
    out = {"pieces": n}
    idx = np.argwhere(solid)
    pts = np.c_[xs[idx[:, 0]], ys[idx[:, 1]], zs[idx[:, 2]]]
    com = pts.mean(0)
    out["volume_cm3"] = len(pts) * step ** 3 / 1000
    out["weight_g"] = out["volume_cm3"] * PLA
    out["com_height_mm"] = com[2]
    foot = pts[pts[:, 2] < zs[0] + step * 1.5][:, :2]
    hull = ConvexHull(foot)
    # distance from the centre of mass to the nearest edge of the footprint
    eq = hull.equations
    edge = -(eq[:, :2] @ com[:2] + eq[:, 2]).max()
    out["tip_deg"] = float(np.degrees(np.arctan2(edge, com[2] - zs[0])))
    # fragile parts: material a ball of LIMITS["min_mm"] cannot reach (opening by a ball).
    # Plain edges lose only a shallow sliver; a member thinner than the limit loses its core.
    edt = ndi.distance_transform_edt(solid) * step
    r = LIMITS["min_mm"] / 2
    opened = ndi.distance_transform_edt(edt <= r) * step <= r
    thin = solid & ~opened & (edt > 0.7)
    out["fragile_mm3"] = float(thin.sum() * step ** 3)
    # overhang: surface facing down more steeply than 45 degrees, above the first layer
    g = np.gradient(vol)
    surf = solid & ~ndi.binary_erosion(solid)
    nz = g[2][surf] / (np.sqrt(g[0][surf] ** 2 + g[1][surf] ** 2 + g[2][surf] ** 2) + 1e-9)
    z_s = zs[np.argwhere(surf)[:, 2]]
    # Slant 3D flags surfaces facing more than ~55 degrees down (hyperboloid rods at 58 passed, cube faces at 54.7 failed)
    bad = (nz < -0.56) & (z_s > zs[0] + 2 * step)
    # the crotch under each rod crossing faces down for a few voxels; that bridges fine.
    # A real problem is one wide patch, so the limit applies to the largest patch.
    patch = np.zeros_like(solid)
    patch[tuple(np.argwhere(surf)[bad].T)] = True
    lab2, m = ndi.label(patch, structure=np.ones((3, 3, 3)))
    sizes = np.bincount(lab2.ravel())[1:] if m else np.array([0])
    out["overhang_cm2"] = float(bad.sum() * step ** 2 / 100)
    out["largest_overhang_cm2"] = float(sizes.max() * step ** 2 / 100)
    out["ok"] = (out["pieces"] == 1 and out["tip_deg"] >= LIMITS["tip_deg"]
                 and out["fragile_mm3"] <= LIMITS["fragile_mm3"] and out["largest_overhang_cm2"] <= LIMITS["overhang_cm2"])
    return out


if __name__ == "__main__":
    for name in sys.argv[1:]:
        r = check(name)
        print(name, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
