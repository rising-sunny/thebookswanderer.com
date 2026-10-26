"""A gyroid (a triply periodic minimal surface) as a thin wall cut to a sphere, saved as a printable STL."""
import numpy as np
from skimage import measure

D, CELL, WALL, N = 70.0, 17.5, 1.6, 170          # mm: diameter, period, wall (1.6 suits FDM); grid size


def field():
    r = D / 2 + 1
    x = np.linspace(-r, r, N); X, Y, Z = np.meshgrid(x, x, x, indexing="ij")
    k = 2 * np.pi / CELL
    g = np.sin(k * X) * np.cos(k * Y) + np.sin(k * Y) * np.cos(k * Z) + np.sin(k * Z) * np.cos(k * X)
    grad = k * 1.5                                   # rough |∇g|, turns |g| into a distance in mm
    sheet = np.abs(g) / grad - WALL / 2
    ball = np.sqrt(X ** 2 + Y ** 2 + Z ** 2) - D / 2
    base = -(Z + D / 2 - 4)                          # a flat 4 mm cut so it stands and prints without a raft
    return np.maximum(np.maximum(sheet, ball), base), x[1] - x[0], -r


def save_stl(path, verts, faces):
    tri = verts[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    data = np.zeros(len(faces), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    data["n"], data["v"] = n, tri
    with open(path, "wb") as f:
        f.write(b"gyroid sphere".ljust(80, b" ")); f.write(np.uint32(len(faces)).tobytes()); f.write(data.tobytes())


if __name__ == "__main__":
    vol, step, origin = field()
    verts, faces, _, _ = measure.marching_cubes(vol, 0.0, spacing=(step,) * 3)
    verts += origin
    save_stl("gyroid-sphere.stl", verts, faces)
    np.save("mesh.npy", {"v": verts, "f": faces}, allow_pickle=True)
    print(len(verts), "vertices", len(faces), "triangles")
