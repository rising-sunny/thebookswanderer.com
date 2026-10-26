"""Ray-marched render of the gyroid sphere straight from its formula."""
import numpy as np
from PIL import Image
from gyroid import D, CELL, WALL

k = 2 * np.pi / CELL
def sdf(p):
    x, y, z = p[..., 0], p[..., 1], p[..., 2]
    g = np.sin(k * x) * np.cos(k * y) + np.sin(k * y) * np.cos(k * z) + np.sin(k * z) * np.cos(k * x)
    return np.maximum(np.abs(g) / (k * 1.5) - WALL / 2, np.linalg.norm(p, axis=-1) - D / 2)

S = 700; u = np.linspace(-45, 45, S)
U, V = np.meshgrid(u, -u)
a, b = 0.5, 0.7
R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]]) @ np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
ro = np.stack([U, V, np.full_like(U, -120)], -1) @ R.T
rd = np.broadcast_to(np.array([0, 0, 1.0]) @ R.T, ro.shape)
t = np.full(U.shape, 60.0); hit = np.zeros(U.shape, bool)
for _ in range(400):
    p = ro + rd * t[..., None]; dist = sdf(p)
    hit |= dist < 0.02
    t = np.where(hit, t, t + np.maximum(dist * 0.6, 0.02))
p = ro + rd * t[..., None]; e = 0.05
n = np.stack([sdf(p + [e, 0, 0]) - sdf(p - [e, 0, 0]), sdf(p + [0, e, 0]) - sdf(p - [0, e, 0]), sdf(p + [0, 0, e]) - sdf(p - [0, 0, e])], -1)
n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
L = np.array([-0.5, 0.7, -0.6]) @ R.T; L /= np.linalg.norm(L)
diff = np.clip((n * L).sum(-1), 0, 1)
# cheap occlusion: how open the space is just outside the surface
ao = np.clip(sdf(p + n * 1.5) / 1.5, 0, 1) * 0.5 + np.clip(sdf(p + n * 4) / 4, 0, 1) * 0.5
shade = (0.18 + 0.82 * diff) * (0.35 + 0.65 * ao)
base = np.array([196, 120, 72]) / 255
img = np.where(hit[..., None], shade[..., None] * base, np.array([244, 239, 228]) / 255)
Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save("gyroid.jpg", quality=92)
print(hit.mean())
