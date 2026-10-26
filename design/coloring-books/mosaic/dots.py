"""Dot-to-dot from an Audubon plate: the bird's outline plus its main inner shapes,
each traced as a run of numbered dots; numbering continues from one run to the next."""
import sys, numpy as np, cv2
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont

FONTS = "/home/user/thebookswanderer.com/server/social/fonts"
DPI = 300
mm = lambda v: v / 25.4 * DPI


def bird_mask(rgb, thin=0):
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    paper = np.median(np.concatenate([lab[:8].reshape(-1, 3), lab[:, :8].reshape(-1, 3)]), 0)
    m = np.linalg.norm(lab - paper, axis=-1) > 18
    m = ndi.binary_closing(m, np.ones((9, 9)), iterations=2)
    m = ndi.binary_fill_holes(m)
    m = ndi.binary_opening(m, np.ones((5, 5)))
    if thin:   # drop twigs and stems thinner than `thin` px
        disk = np.hypot(*np.mgrid[-thin:thin + 1, -thin:thin + 1]) <= thin
        m = ndi.binary_opening(m, disk)
    lab_, n = ndi.label(m)
    sizes = ndi.sum(m, lab_, range(1, n + 1))
    return lab_ == (np.argmax(sizes) + 1)


def regions(rgb, mask, k=4, min_frac=0.06):
    """Large single-colour areas inside the bird (breast, wing...), as masks."""
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 4), cv2.COLOR_RGB2LAB).astype(np.float32)
    px = lab[mask]
    _, lbl, _ = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1), 4, cv2.KMEANS_PP_CENTERS)
    full = np.full(mask.shape, -1); full[mask] = lbl[:, 0]
    out = []
    for c in range(k):
        r = ndi.binary_opening(full == c, np.ones((9, 9)))
        r = ndi.binary_closing(r, np.ones((9, 9)))
        lab_, n = ndi.label(r)
        for i in range(1, n + 1):
            part = lab_ == i
            if part.sum() > min_frac * mask.sum():
                out.append(ndi.binary_fill_holes(part))
    return out


def resample(c, spacing, eps, closed):
    corners = cv2.approxPolyDP(c.astype(np.float32).reshape(-1, 1, 2), eps, closed)[:, 0, :]
    ring = np.vstack([corners, corners[:1]]) if closed else corners
    pts = [ring[0]]
    for a, b in zip(ring[:-1], ring[1:]):
        L = np.hypot(*(b - a)); n = max(1, int(np.ceil(L / spacing)))
        pts += [a + (b - a) * t for t in np.arange(1, n + 1) / n]
    return np.array(pts[:-1] if closed else pts)


def outline(m):
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cnts, key=cv2.contourArea)[:, 0, :].astype(float)


def inner_lines(region, depth, min_gap, min_len):
    """The parts of a region's edge that lie inside the bird, as open lines."""
    c = outline(region)
    inside = depth[c[:, 1].astype(int), c[:, 0].astype(int)] > min_gap
    if inside.all() or not inside.any():
        return [c] if inside.all() else []
    k = int(np.argmin(inside)); c, inside = np.roll(c, -k, 0), np.roll(inside, -k)   # start outside
    runs, cur = [], []
    for p, ok in zip(c, inside):
        if ok: cur.append(p)
        elif cur: runs.append(np.array(cur)); cur = []
    if cur: runs.append(np.array(cur))
    return [r for r in runs if np.hypot(*np.diff(r, axis=0).T).sum() > min_len]


def build(src, crop, out, title, credit, spacing_mm=4.0, thin=0):
    im = Image.open(src).convert("RGB"); W, H = im.size
    im = im.crop((int(crop[0] * W), int(crop[1] * H), int(crop[2] * W), int(crop[3] * H)))
    rgb = np.asarray(im)
    mask = bird_mask(rgb, thin)
    ys, xs = np.where(mask)
    box_w, box_h = mm(176), mm(225)
    sc = min(box_w / (xs.max() - xs.min()), box_h / (ys.max() - ys.min()))
    PW, PH = int(mm(210)), int(mm(297))
    ox = (PW - (xs.max() - xs.min()) * sc) / 2 - xs.min() * sc
    oy = mm(36) + (box_h - (ys.max() - ys.min()) * sc) / 2 - ys.min() * sc
    sp, eps = mm(spacing_mm) / sc, mm(1.2) / sc
    runs = [resample(outline(mask), sp, eps, True)]
    closed = [True]
    depth = ndi.distance_transform_edt(mask)
    lines = []
    for r in sorted(regions(rgb, mask), key=lambda r: -r.sum())[:4]:
        if r.sum() < 0.9 * mask.sum():
            lines += inner_lines(r, depth, mm(2.5) / sc, mm(30) / sc)
    # each boundary is shared by two regions: keep a line only if it is not already traced
    kept = []
    for ln in sorted(lines, key=len, reverse=True):
        if all(np.min(np.hypot(*(o[:, None, :] - ln[None, ::5, :]).transpose(2, 0, 1)), axis=0).mean() > mm(3) / sc for o in kept):
            kept.append(ln)
    for ln in kept[:3]:
        runs.append(resample(ln, sp, eps, False)); closed.append(False)
    runs = [r * sc + [ox, oy] for r in runs]
    total = sum(len(r) for r in runs)
    print(title, [len(r) for r in runs], "dots:", total)

    font = ImageFont.truetype(f"{FONTS}/Karla-400.ttf", int(5.5 / 72 * DPI))
    serif = ImageFont.truetype(f"{FONTS}/Playfair-600.ttf", int(20 / 72 * DPI))
    italic = ImageFont.truetype(f"{FONTS}/Playfair-500i.ttf", int(10.5 / 72 * DPI))
    allpts = np.vstack(runs)
    pages = {}
    for mode in ("dots", "solution"):
        page = Image.new("RGB", (PW, PH), "white"); d = ImageDraw.Draw(page)
        d.text((PW / 2, mm(20)), title, font=serif, fill=(30, 40, 35), anchor="mm")
        d.text((PW / 2, mm(27)), credit, font=italic, fill=(110, 110, 105), anchor="mm")
        taken = []
        n = 0; r_dot = mm(0.45)
        for run in runs:
            if mode == "solution":
                ring = np.vstack([run, run[:1]]) if run is runs[0] else run
                d.line([tuple(p) for p in ring], fill=(40, 40, 40), width=4)
                continue
            for i, p in enumerate(run):
                n += 1
                if i == 0:   # a new run starts at a small open circle
                    d.ellipse((p[0] - mm(1.1), p[1] - mm(1.1), p[0] + mm(1.1), p[1] + mm(1.1)), outline=(0, 0, 0), width=3)
                d.ellipse((p[0] - r_dot, p[1] - r_dot, p[0] + r_dot, p[1] + r_dot), fill=(0, 0, 0))
                # put the number where it touches no dot and no other number
                label = str(n); tw = d.textlength(label, font=font); th = mm(2)
                best = None
                for ang in np.linspace(0, 2 * np.pi, 16, endpoint=False):
                    for rad in (mm(1.8), mm(2.6), mm(3.4)):
                        cx, cy = p[0] + rad * np.cos(ang), p[1] + rad * np.sin(ang)
                        bx = (cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2)
                        near = np.abs(allpts - [cx, cy])
                        clash = ((near[:, 0] < tw / 2 + mm(0.6)) & (near[:, 1] < th / 2 + mm(0.6))).any()
                        clash |= any(not (bx[2] < t[0] or bx[0] > t[2] or bx[3] < t[1] or bx[1] > t[3]) for t in taken)
                        if not clash:
                            best = bx; break
                    if best: break
                if best is None:
                    cx, cy = p[0] + mm(1.8), p[1]; best = (cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2)
                taken.append(best)
                d.text(((best[0] + best[2]) / 2, (best[1] + best[3]) / 2), label, font=font, fill=(60, 60, 60), anchor="mm")
        note = "Start at the circle. Join the dots in order; a new circle starts a new line." if mode == "dots" else "The finished outline"
        d.text((PW / 2, PH - mm(18)), note, font=italic, fill=(120, 120, 115), anchor="mm")
        page.save(f"{out}-{mode}.png"); pages[mode] = page
    return pages


if __name__ == "__main__":
    A = "After John James Audubon, Birds of America, plate "
    build("../lp/aud/plate-358-pine-grosbeak.jpg", (0.13, 0.45, 0.58, 0.78), "grosbeak", "Pine Grosbeak", A + "358", thin=14)
