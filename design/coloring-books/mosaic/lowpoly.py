"""Adaptive low-poly colour-by-number from a picture on a plain background.

Points are denser along edges and details (variable-radius dart throwing),
joined by Delaunay; each triangle takes the mean colour under it, colours are
reduced to a K-colour palette (k-means in Lab) and every triangle is numbered.
"""
import sys, math
import numpy as np, cv2
from scipy.spatial import Delaunay, cKDTree
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"


def subject_mask(rgb):
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    border = np.concatenate([lab[:10].reshape(-1, 3), lab[-10:].reshape(-1, 3), lab[:, :10].reshape(-1, 3), lab[:, -10:].reshape(-1, 3)])
    paper = np.median(border, 0)
    m = np.linalg.norm(lab - paper, axis=-1) > 22
    m = ndi.binary_closing(m, np.ones((9, 9)))
    m = ndi.binary_fill_holes(m)
    m = ndi.binary_opening(m, np.ones((7, 7)))
    lab_, n = ndi.label(m)
    sizes = ndi.sum(m, lab_, range(1, n + 1))
    keep = np.zeros(n + 1, bool); keep[1:] = sizes > 0.01 * m.sum()
    return keep[lab_]


def sample_points(rgb, mask, rmin, rmax, seed=1):
    lab = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32), (0, 0), 2)
    e = 0
    for ch in range(3):
        gx, gy = cv2.Sobel(lab[..., ch], cv2.CV_32F, 1, 0), cv2.Sobel(lab[..., ch], cv2.CV_32F, 0, 1)
        e = e + np.hypot(gx, gy) * (1.0 if ch == 0 else 1.6)
    e = cv2.GaussianBlur(e, (0, 0), 3)
    e = np.clip(e / np.percentile(e[mask], 97), 0, 1)
    # silhouette points first, so the outline is clean
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pts = []
    step = rmin * 1.8
    for c in cnts:
        c = cv2.approxPolyDP(c, 2.5, True)[:, 0, :].astype(float)
        c = np.vstack([c, c[:1]])
        seg = np.hypot(*np.diff(c, axis=0).T); cum = np.concatenate([[0], np.cumsum(seg)])
        for d in np.arange(0, cum[-1], step):
            i = min(np.searchsorted(cum, d, side="right") - 1, len(seg) - 1)
            t = (d - cum[i]) / max(seg[i], 1e-9)
            pts.append(tuple(c[i] + t * (c[i + 1] - c[i])))
    # interior points keep clear of the outline, or the rim fills with slivers
    rim = ndi.distance_transform_edt(mask)
    rng = np.random.default_rng(seed)
    ys, xs = np.where(mask)
    order = rng.permutation(len(xs))[:200000]
    cand = np.stack([xs[order], ys[order]], 1).astype(float)
    w = e[ys[order], xs[order]]
    cand = cand[np.argsort(-(w + rng.random(len(w)) * 0.15))]
    acc = list(pts)
    tree_pts = list(pts)
    grid = {}
    cell = rmin
    def key(p): return (int(p[0] // cell), int(p[1] // cell))
    for p in acc: grid.setdefault(key(p), []).append(p)
    for p in cand:
        r = rmin + (rmax - rmin) * (1 - e[int(p[1]), int(p[0])]) ** 2.2
        if rim[int(p[1]), int(p[0])] < step * 0.75:
            continue
        kx, ky = key(p); k = int(math.ceil(r / cell))
        ok = True
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1):
                for q in grid.get((kx + dx, ky + dy), ()):
                    if (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 < r * r:
                        ok = False; break
                if not ok: break
            if not ok: break
        if ok:
            acc.append(tuple(p)); grid.setdefault((kx, ky), []).append(tuple(p))
    return np.array(acc)


def triangulate(points, mask):
    tri = Delaunay(points)
    simp = tri.simplices
    cent = points[simp].mean(1)
    inside = mask[np.clip(cent[:, 1].astype(int), 0, mask.shape[0] - 1), np.clip(cent[:, 0].astype(int), 0, mask.shape[1] - 1)]
    return simp[inside]


def tri_colors(rgb, points, simp):
    out = []
    for t in simp:
        poly = points[t].astype(np.int32)
        x0, y0 = poly.min(0); x1, y1 = poly.max(0) + 1
        m = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillConvexPoly(m, poly - [x0, y0], 1)
        px = rgb[y0:y1, x0:x1][m.astype(bool)]
        out.append(px.mean(0) if len(px) else rgb[int(poly[:, 1].mean()), int(poly[:, 0].mean())])
    return np.array(out)


def palette(colors, areas, k):
    lab = cv2.cvtColor(colors.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    w = np.repeat(lab, np.maximum(1, (areas / areas.mean() * 3).astype(int)), 0)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.5)
    _, _, centers = cv2.kmeans(w, k, None, crit, 6, cv2.KMEANS_PP_CENTERS)
    centers = centers[np.argsort(-centers[:, 0])]  # light to dark
    idx = cKDTree(centers).query(lab)[1]
    rgbc = cv2.cvtColor(centers.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2RGB).reshape(-1, 3)
    return idx, rgbc


def inradius(p):
    a, b, c = (np.linalg.norm(p[1] - p[2]), np.linalg.norm(p[0] - p[2]), np.linalg.norm(p[0] - p[1]))
    s = (a + b + c) / 2
    area = max(1e-9, s * (s - a) * (s - b) * (s - c)) ** 0.5
    return area / s, (a * p[0] + b * p[1] + c * p[2]) / (a + b + c)


def hue_mask(rgb):
    """Saturated pinks and reds plus the dark bill, for a bird on a painted landscape."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(int)
    h, sat, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = ((h > 150) | (h < 12)) & (sat > 70) & (v > 60)
    m = ndi.binary_closing(m, np.ones((15, 15)))
    m = ndi.binary_fill_holes(m)
    m = ndi.binary_opening(m, np.ones((5, 5)))
    lab_, n = ndi.label(m)
    sizes = ndi.sum(m, lab_, range(1, n + 1))
    return lab_ == (np.argmax(sizes) + 1)


def build(src, crop, out, title, k=16, work_w=1400, rmin=18, rmax=80, mask_fn=subject_mask):
    im = Image.open(src).convert("RGB")
    W0, H0 = im.size
    im = im.crop((int(crop[0] * W0), int(crop[1] * H0), int(crop[2] * W0), int(crop[3] * H0)))
    im = im.resize((work_w, int(work_w * im.height / im.width)), Image.LANCZOS)
    rgb = np.asarray(im)
    mask = mask_fn(rgb)
    pts = sample_points(rgb, mask, rmin, rmax)
    simp = triangulate(pts, mask)
    cols = tri_colors(rgb, pts, simp)
    u, v = pts[simp[:, 1]] - pts[simp[:, 0]], pts[simp[:, 2]] - pts[simp[:, 0]]
    areas = np.abs(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]) / 2
    idx, pal = palette(cols, areas, k)
    print(title, "points", len(pts), "triangles", len(simp))

    # render at 300 dpi on Letter: art box 7.5 x 8.2 in, key below
    DPI = 300; PW, PH = int(8.5 * DPI), int(11 * DPI)
    box_w, box_h = int(7.5 * DPI), int(7.9 * DPI)
    ys, xs = np.where(mask); bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max(), ys.max()
    sc = min(box_w / (bx1 - bx0), box_h / (by1 - by0))
    ox = (PW - (bx1 - bx0) * sc) / 2 - bx0 * sc; oy = int(1.15 * DPI) - by0 * sc
    P = pts * sc + [ox, oy]
    serif = lambda s: ImageFont.truetype(f"{FONTS}/Playfair-600.ttf", s)
    sans = lambda s: ImageFont.truetype(f"{FONTS}/Karla-700.ttf", s)
    pages = {}
    for mode in ("color", "solution"):
        page = Image.new("RGB", (PW, PH), "white"); d = ImageDraw.Draw(page)
        d.text((PW / 2, 0.62 * DPI), title, font=serif(96), fill=(30, 40, 35), anchor="mm")
        for t, ci in zip(simp, idx):
            poly = [tuple(P[v]) for v in t]
            if mode == "solution":
                d.polygon(poly, fill=tuple(int(c) for c in pal[ci]), outline=tuple(int(c) for c in pal[ci]))
            else:
                d.polygon(poly, fill="white", outline=(150, 150, 150), width=2)
        if mode == "color":
            for t, ci in zip(simp, idx):
                r, c = inradius(P[t])
                fs = int(max(17, min(44, r * 1.15)))
                d.text(tuple(c), str(ci + 1), font=sans(fs), fill=(90, 90, 90), anchor="mm")
        # colour key
        n = len(pal); per = 8; sw = 120; gapx = (PW - 2 * 0.6 * DPI) / per
        ky = int(PH - 1.55 * DPI)
        for i, c in enumerate(pal):
            row, col = divmod(i, per)
            x = 0.6 * DPI + col * gapx + (gapx - sw) / 2; y = ky + row * (sw + 70)
            d.rectangle((x, y, x + sw, y + sw), fill=tuple(int(v) for v in c), outline=(80, 80, 80), width=3)
            d.text((x + sw / 2, y + sw + 32), str(i + 1), font=sans(40), fill=(50, 50, 50), anchor="mm")
        pages[mode] = page
        page.save(f"{out}-{mode}.png", dpi=(DPI, DPI))
    return len(simp), pal


if __name__ == "__main__":
    build("plate-61-great-horned-owl.jpg", (0.06, 0.11, 0.86, 0.87), "owl", "Great Horned Owl")
    build("plate-431-american-flamingo.jpg", (0.12, 0.17, 0.88, 0.87), "flamingo", "American Flamingo", mask_fn=hue_mask)
