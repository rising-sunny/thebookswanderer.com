"""Low-poly colour-by-number sized for coloured pencils.

Works in page units: the subject is scaled to the art box first, so every rule
is in millimetres. Thin parts are widened, no triangle is smaller than a 5 mm
circle, numbers are at least 7.5 pt, and the palette has at most 12 clearly
different colours. Pages come in pairs: solution + key (left), page to colour (right).
"""
import math
import numpy as np, cv2
from scipy.spatial import Delaunay, cKDTree
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont
from lowpoly import subject_mask, hue_mask, tri_colors, inradius, FONTS

PXMM = 4                     # working pixels per millimetre
DPI = 300
PAGE = (8.5 * 25.4, 11 * 25.4)
ART = (190.0, 196.0)         # art box, mm
MIN_R = 2.5                  # smallest inscribed circle radius, mm (5 mm circle)
MIN_PT = 7.5                 # smallest number, points


def prepare(src, crop, mask_fn):
    im = Image.open(src).convert("RGB"); W0, H0 = im.size
    im = im.crop((int(crop[0] * W0), int(crop[1] * H0), int(crop[2] * W0), int(crop[3] * H0)))
    small = im.resize((1400, int(1400 * im.height / im.width)), Image.LANCZOS)
    m = mask_fn(np.asarray(small))
    ys, xs = np.where(m)
    bw, bh = (xs.max() - xs.min()) / 1400 * im.width, (ys.max() - ys.min()) / 1400 * im.width
    s = min(ART[0] / bw, ART[1] / bh) * PXMM          # source px -> working px
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    rgb = np.asarray(im)
    mask = cv2.resize(m.astype(np.uint8), (im.width, im.height), interpolation=cv2.INTER_NEAREST).astype(bool)
    # widen anything narrower than ~12 mm (legs, bills, twigs)
    core = ndi.distance_transform_edt(mask) > 6 * PXMM
    opened = ndi.distance_transform_edt(~core) <= 6 * PXMM
    disk = lambda r: np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r
    thin = ndi.binary_opening(mask & ~opened, structure=disk(int(1.5 * PXMM)))
    wide = mask | (ndi.distance_transform_edt(~thin) <= 3.5 * PXMM)
    # colours outside the original subject come from its nearest pixel
    idx = ndi.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    rgb = rgb[idx[0], idx[1]]
    wide = ndi.binary_opening(ndi.binary_closing(wide, structure=disk(2 * PXMM)), structure=disk(PXMM))
    return rgb, ndi.binary_fill_holes(wide)


def edges(rgb, mask):
    lab = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32), (0, 0), 1.5 * PXMM)
    e = 0
    for ch in range(3):
        gx, gy = cv2.Sobel(lab[..., ch], cv2.CV_32F, 1, 0), cv2.Sobel(lab[..., ch], cv2.CV_32F, 0, 1)
        e = e + np.hypot(gx, gy) * (1.0 if ch == 0 else 1.6)
    e = cv2.GaussianBlur(e, (0, 0), 2 * PXMM)
    return np.clip(e / np.percentile(e[mask], 97), 0, 1)


def sample(rgb, mask, dmin, dmax, outline, seed=1):
    e = edges(rgb, mask)
    pts, fixed = [], []
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for c in cnts:
        c = cv2.approxPolyDP(c, 0.6 * PXMM, True)[:, 0, :].astype(float)
        c = np.vstack([c, c[:1]])
        seg = np.hypot(*np.diff(c, axis=0).T); cum = np.concatenate([[0], np.cumsum(seg)])
        for d in np.arange(0, cum[-1], outline):
            i = min(np.searchsorted(cum, d, side="right") - 1, len(seg) - 1)
            pts.append(c[i] + (d - cum[i]) / max(seg[i], 1e-9) * (c[i + 1] - c[i]))
    fixed = len(pts)
    rim = ndi.distance_transform_edt(mask)
    rng = np.random.default_rng(seed)
    ys, xs = np.where(mask)
    order = rng.permutation(len(xs))[:150000]
    cand = np.stack([xs[order], ys[order]], 1).astype(float)
    w = e[ys[order], xs[order]]
    cand = cand[np.argsort(-(w + rng.random(len(w)) * 0.2))]
    tree = cKDTree(np.array(pts))
    acc = list(pts); extra = []
    for p in cand:
        if rim[int(p[1]), int(p[0])] < outline * 0.7:
            continue
        r = dmin + (dmax - dmin) * (1 - e[int(p[1]), int(p[0])]) ** 2
        if tree.query_ball_point(p, r):
            continue
        if extra and min(np.hypot(*(np.array(extra[-400:]) - p).T)) < r and cKDTree(extra).query_ball_point(p, r):
            continue
        if extra and cKDTree(extra).query_ball_point(p, r):
            continue
        extra.append(p)
    return np.array(acc + extra), fixed


def sample_fast(rgb, mask, dmin, dmax, outline, seed=1):
    """Same as sample() with a grid instead of rebuilding trees."""
    e = edges(rgb, mask)
    pts = []
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for c in cnts:
        c = cv2.approxPolyDP(c, 0.6 * PXMM, True)[:, 0, :].astype(float)
        c = np.vstack([c, c[:1]])
        seg = np.hypot(*np.diff(c, axis=0).T); cum = np.concatenate([[0], np.cumsum(seg)])
        for d in np.arange(0, cum[-1], outline):
            i = min(np.searchsorted(cum, d, side="right") - 1, len(seg) - 1)
            pts.append(tuple(c[i] + (d - cum[i]) / max(seg[i], 1e-9) * (c[i + 1] - c[i])))
    fixed = len(pts)
    rim = ndi.distance_transform_edt(mask)
    rng = np.random.default_rng(seed)
    ys, xs = np.where(mask)
    order = rng.permutation(len(xs))[:150000]
    cand = np.stack([xs[order], ys[order]], 1).astype(float)
    w = e[ys[order], xs[order]]
    cand = cand[np.argsort(-(w + rng.random(len(w)) * 0.2))]
    cell = dmin; grid = {}
    key = lambda p: (int(p[0] // cell), int(p[1] // cell))
    for p in pts: grid.setdefault(key(p), []).append(p)
    for p in cand:
        if rim[int(p[1]), int(p[0])] < outline * 0.7:
            continue
        r = dmin + (dmax - dmin) * (1 - e[int(p[1]), int(p[0])]) ** 2
        kx, ky = key(p); k = int(math.ceil(r / cell)); ok = True
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1):
                for q in grid.get((kx + dx, ky + dy), ()):
                    if (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 < r * r:
                        ok = False; break
                if not ok: break
            if not ok: break
        if ok:
            pts.append(tuple(p)); grid.setdefault((kx, ky), []).append(tuple(p))
    return np.array(pts), fixed


def triangulate(pts, mask):
    simp = Delaunay(pts).simplices
    c = pts[simp].mean(1)
    ok = mask[np.clip(c[:, 1].astype(int), 0, mask.shape[0] - 1), np.clip(c[:, 0].astype(int), 0, mask.shape[1] - 1)]
    return simp[ok]


def inr(pts, simp):
    p = pts[simp]
    a = np.linalg.norm(p[:, 1] - p[:, 2], axis=1); b = np.linalg.norm(p[:, 0] - p[:, 2], axis=1); c = np.linalg.norm(p[:, 0] - p[:, 1], axis=1)
    s = (a + b + c) / 2
    return np.sqrt(np.maximum(s * (s - a) * (s - b) * (s - c), 0)) / s


def relax(pts, fixed, mask, dens, iters=6):
    """Lloyd-style smoothing: move each free point to the density-weighted mean of
    its Delaunay neighbours, so triangles get close to equilateral."""
    pts = pts.copy()
    for _ in range(iters):
        simp = Delaunay(pts).simplices
        acc = np.zeros_like(pts); wsum = np.zeros(len(pts))
        cen = pts[simp].mean(1)
        w = dens[np.clip(cen[:, 1].astype(int), 0, mask.shape[0] - 1), np.clip(cen[:, 0].astype(int), 0, mask.shape[1] - 1)] + 0.2
        for k in range(3):
            np.add.at(acc, simp[:, k], cen * w[:, None]); np.add.at(wsum, simp[:, k], w)
        new = acc / np.maximum(wsum, 1e-9)[:, None]
        new[:fixed] = pts[:fixed]
        ok = mask[np.clip(new[:, 1].astype(int), 0, mask.shape[0] - 1), np.clip(new[:, 0].astype(int), 0, mask.shape[1] - 1)]
        pts[ok] = new[ok]
    return pts


def remove_slivers(pts, fixed, mask, rmin):
    keep = np.ones(len(pts), bool)
    for _ in range(60):
        idx = np.where(keep)[0]; P = pts[idx]
        simp = triangulate(P, mask)
        r = inr(P, simp)
        bad = simp[r < rmin]
        if not len(bad):
            return P, simp
        drop = set()
        for t in bad:
            if any(idx[v] in drop for v in t):
                continue
            free = [v for v in t if idx[v] >= fixed] or list(t)
            # drop the vertex on the shortest edge
            e = [(np.linalg.norm(P[t[(i + 1) % 3]] - P[t[(i + 2) % 3]]), i) for i in range(3)]
            short = min(e)[1]; ends = [t[(short + 1) % 3], t[(short + 2) % 3]]
            pick = [v for v in ends if v in free] or free
            drop.add(idx[pick[0]])
        keep[list(drop)] = False
    idx = np.where(keep)[0]; P = pts[idx]
    return P, triangulate(P, mask)


def palette(cols, areas, k, merge=8.0):
    lab = cv2.cvtColor(cols.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    lab[:, 0] *= 100 / 255; lab[:, 1:] -= 128
    w = np.repeat(lab, np.maximum(1, (areas / areas.mean() * 3).astype(int)), 0)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 80, 0.2)
    _, _, cen = cv2.kmeans(w, k, None, crit, 8, cv2.KMEANS_PP_CENTERS)
    cen = list(cen)
    while True:  # merge colours too close to tell apart with pencils
        d = [(np.linalg.norm(cen[i] - cen[j]), i, j) for i in range(len(cen)) for j in range(i + 1, len(cen))]
        dm, i, j = min(d)
        if dm >= merge: break
        cen[i] = (cen[i] + cen[j]) / 2; cen.pop(j)
    cen = np.array(cen); cen = cen[np.argsort(-cen[:, 0])]
    idx = cKDTree(cen).query(lab)[1]
    used = np.unique(idx); remap = {u: n for n, u in enumerate(used)}
    cen = cen[used]; idx = np.array([remap[i] for i in idx])
    lab8 = np.stack([cen[:, 0] * 255 / 100, cen[:, 1] + 128, cen[:, 2] + 128], 1).clip(0, 255).astype(np.uint8)
    rgb = cv2.cvtColor(lab8.reshape(-1, 1, 3), cv2.COLOR_LAB2RGB).reshape(-1, 3)
    return idx, rgb


def mm2px(v):
    return v / 25.4 * DPI


def render(pts, simp, idx, pal, title, latin, out):
    PW, PH = int(mm2px(PAGE[0])), int(mm2px(PAGE[1]))
    lo = pts[simp].reshape(-1, 2).min(0); hi = pts[simp].reshape(-1, 2).max(0)
    size = (hi - lo) / PXMM
    off = np.array([(PAGE[0] - size[0]) / 2, 30 + (ART[1] - size[1]) / 2])
    P = mm2px((pts - lo) / PXMM + off)
    serif = lambda s: ImageFont.truetype(f"{FONTS}/Playfair-600.ttf", s)
    italic = lambda s: ImageFont.truetype(f"{FONTS}/Playfair-500i.ttf", s)
    sans = lambda s: ImageFont.truetype(f"{FONTS}/Karla-700.ttf", s)
    pt = lambda v: int(v / 72 * DPI)
    pages = []
    for mode in ("solution", "color"):
        page = Image.new("RGB", (PW, PH), "white"); d = ImageDraw.Draw(page)
        d.text((PW / 2, mm2px(14)), title, font=serif(pt(20)), fill=(30, 40, 35), anchor="mm")
        d.text((PW / 2, mm2px(21)), latin, font=italic(pt(10.5)), fill=(110, 110, 105), anchor="mm")
        for t, ci in zip(simp, idx):
            poly = [tuple(P[v]) for v in t]
            if mode == "solution":
                col = tuple(int(c) for c in pal[ci]); d.polygon(poly, fill=col, outline=col)
            else:
                d.polygon(poly, fill="white", outline=(150, 150, 150), width=2)
        if mode == "color":
            for t, ci in zip(simp, idx):
                r, c = inradius(P[t])
                fs = int(min(max(pt(MIN_PT), r * 0.85), pt(12)))
                d.text(tuple(c), str(ci + 1), font=sans(fs), fill=(105, 105, 105), anchor="mm")
        # key: one row of swatches
        n = len(pal); sw = mm2px(11); gap = (mm2px(PAGE[0] - 30) - n * sw) / max(1, n - 1)
        y = mm2px(PAGE[1] - 36)
        for i, c in enumerate(pal):
            x = mm2px(15) + i * (sw + gap)
            d.rectangle((x, y, x + sw, y + sw), fill=tuple(int(v) for v in c), outline=(90, 90, 90), width=3)
            d.text((x + sw / 2, y + sw + mm2px(4.5)), str(i + 1), font=sans(pt(11)), fill=(50, 50, 50), anchor="mm")
        if mode == "solution":
            d.text((PW / 2, mm2px(PAGE[1] - 12)), "The finished picture and its colours", font=italic(pt(9)), fill=(120, 120, 115), anchor="mm")
        else:
            d.text((PW / 2, mm2px(PAGE[1] - 12)), "Colour each shape with the colour of its number", font=italic(pt(9)), fill=(120, 120, 115), anchor="mm")
        page.save(f"{out}-{mode}.png", dpi=(DPI, DPI)); pages.append(page)
    return pages


def build(src, crop, out, title, latin, dmax_mm, dmin_mm=9.5, outline_mm=10, mask_fn=subject_mask, k=12, merge=8.0):
    rgb, mask = prepare(src, crop, mask_fn)
    pts, fixed = sample_fast(rgb, mask, dmin_mm * PXMM, dmax_mm * PXMM, outline_mm * PXMM)
    pts = relax(pts, fixed, mask, edges(rgb, mask))
    pts, simp = remove_slivers(pts, fixed, mask, MIN_R * PXMM)
    cols = tri_colors(rgb, pts, simp)
    u, v = pts[simp[:, 1]] - pts[simp[:, 0]], pts[simp[:, 2]] - pts[simp[:, 0]]
    areas = np.abs(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]) / 2
    idx, pal = palette(cols, areas, k, merge)
    r = inr(pts, simp) / PXMM
    print(f"{title}: {len(simp)} triangles, {len(pal)} colours, smallest circle {2 * r.min():.1f} mm, median {2 * np.median(r):.1f} mm")
    return render(pts, simp, idx, pal, title, latin, out)


if __name__ == "__main__":
    pages = build("plate-351-great-cinereous-owl.jpg", (0.15, 0.16, 0.52, 0.52), "owl2", "Great Grey Owl", "after John James Audubon, Birds of America, plate 351", 14, merge=4.0)
    pages += build("plate-431-american-flamingo.jpg", (0.12, 0.17, 0.88, 0.87), "flamingo2", "American Flamingo", "after John James Audubon, Birds of America, plate 431", 13, mask_fn=hue_mask)
    pages[0].save("lowpoly-sample.pdf", save_all=True, append_images=pages[1:], resolution=DPI)
