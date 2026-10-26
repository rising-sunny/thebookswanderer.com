"""Ray-marched preview of a sculpture SDF, standing on its base, seen from a little above."""
import sys, numpy as np
from PIL import Image
from sculptures import DESIGNS

def render(name, S=420, color=(196, 120, 72)):
    f, box, _ = DESIGNS[name]
    x0, x1, y0, y1, z0, z1 = box
    c = np.array([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]); span = max(x1 - x0, z1 - z0) * 1.25
    el = 0.32
    fwd = np.array([0.0, np.cos(el), -np.sin(el)])      # looking a little down
    up = np.array([0.0, np.sin(el), np.cos(el)]); right = np.cross(fwd, up)
    u = np.linspace(-span / 2, span / 2, S); U, V = np.meshgrid(u, -u)
    ro = c - fwd * 200 + U[..., None] * right + V[..., None] * up
    ro = ro.reshape(-1, 3); rd = np.broadcast_to(fwd, ro.shape)
    t = np.full(len(ro), 120.0); hit = np.zeros(len(ro), bool); alive = np.ones(len(ro), bool)
    for _ in range(320):
        idx = np.where(alive)[0]
        if not len(idx): break
        p = ro[idx] + rd[idx] * t[idx, None]; d = f(p)
        h = d < 0.03; hit[idx[h]] = True; alive[idx[h]] = False
        t[idx] += np.maximum(d * 0.7, 0.04)
        alive[idx[t[idx] > 300]] = False
    p = ro + rd * t[:, None]; e = 0.06; n = np.zeros_like(p)
    for i in range(3):
        o = np.zeros(3); o[i] = e; n[:, i] = f(p + o) - f(p - o)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    L = np.array([-0.5, -0.6, 0.65]); L /= np.linalg.norm(L)
    diff = np.clip(n @ L, 0, 1)
    ao = np.clip(f(p + n * 2) / 2, 0, 1) * 0.5 + np.clip(f(p + n * 5) / 5, 0, 1) * 0.5
    shade = (0.2 + 0.8 * diff) * (0.4 + 0.6 * ao)
    img = np.where(hit[:, None], shade[:, None] * np.array(color) / 255, np.array([244, 239, 228]) / 255)
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8).reshape(S, S, 3))

if __name__ == "__main__":
    for n in sys.argv[1:] or DESIGNS:
        render(n).save(f"r-{n}.png"); print(n)
