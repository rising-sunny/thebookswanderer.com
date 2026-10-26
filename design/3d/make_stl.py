"""Mesh a sculpture SDF into one connected STL (marching cubes)."""
import sys, numpy as np
from scipy import ndimage as ndi
from skimage import measure
from sculptures import DESIGNS
from gyroid import save_stl

name, step = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.35
f, (x0, x1, y0, y1, z0, z1), _ = DESIGNS[name]
pad = 2 * step
xs = np.arange(x0 - pad, x1 + pad, step); ys = np.arange(y0 - pad, y1 + pad, step); zs = np.arange(z0 - pad, z1 + pad, step)
vol = np.empty((len(xs), len(ys), len(zs)), np.float32)
X, Y = np.meshgrid(xs, ys, indexing="ij")
for k, z in enumerate(zs):
    p = np.stack([X.ravel(), Y.ravel(), np.full(X.size, z)], 1)
    vol[:, :, k] = f(p).reshape(X.shape)
solid, n = ndi.label(vol < 0)
sizes = ndi.sum(np.ones_like(vol), solid, range(1, n + 1))
vol = np.where(solid == 1 + int(np.argmax(sizes)), vol, np.abs(vol) + step)
verts, faces, _, _ = measure.marching_cubes(vol, 0.0, spacing=(step,) * 3)
verts += [xs[0], ys[0], zs[0]]
verts[:, 2] -= verts[:, 2].min()
save_stl(f"{name}.stl", verts, faces)
print(name, n, "pieces before; kept one;", len(faces), "triangles;", np.ptp(verts, 0).round(1), "mm")
