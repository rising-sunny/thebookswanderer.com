"""Run every candidate plate through the A4 / 4.5 mm mosaic and lay the results out
side by side with the original, to pick the ones that stay recognisable."""
import glob, os, sys
import numpy as np, cv2
from scipy import ndimage as ndi
from PIL import Image, ImageDraw
import mosaic
from lowpoly2 import palette

COLS, ROWS = 43, 52


def auto_crop(path):
    """Fractional crop around the painted subject, widened to the grid's proportions."""
    im = Image.open(path).convert("RGB"); W, H = im.size
    a = np.asarray(im.resize((W // 4, H // 4)))
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32)
    paper = np.median(np.concatenate([lab[:6].reshape(-1, 3), lab[:, :6].reshape(-1, 3)]), 0)
    m = np.linalg.norm(lab - paper, axis=-1) > 20
    h, w = m.shape
    m[: int(h * .06)] = False; m[int(h * .89):] = False          # plate number and lettering
    m = ndi.binary_opening(m, np.ones((5, 5)))
    ys, xs = np.where(m)
    x0, x1 = np.percentile(xs, 0.5) / w, np.percentile(xs, 99.5) / w
    y0, y1 = np.percentile(ys, 0.5) / h, np.percentile(ys, 99.5) / h
    pad = 0.02; x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    want = COLS / ROWS * H / W                                  # in fractional units
    cw, ch = x1 - x0, y1 - y0
    if cw / ch < want:
        d = (want * ch - cw) / 2; x0 -= d; x1 += d
    else:
        d = (cw / want - ch) / 2; y0 -= d; y1 += d
    return (max(0, x0), max(0, y0), min(1, x1), min(1, y1))


def mosaic_preview(path, crop, px=7):
    mosaic.ART_W, mosaic.ART_H = COLS * 4.5, ROWS * 4.5
    small, cols, rows = mosaic.grid(path, crop, 4.5)
    idx, pal = palette(small.reshape(-1, 3).astype(np.float32), np.ones(cols * rows), 14, 7.0)
    idx = mosaic.smooth(idx.reshape(rows, cols))
    img = pal[idx].astype(np.uint8)
    return Image.fromarray(img).resize((cols * px, rows * px), Image.NEAREST), len(np.unique(idx))


if __name__ == "__main__":
    files = sorted(glob.glob("aud/*.jpg"))
    crops = {}
    tiles = []
    for f in files:
        c = auto_crop(f); crops[os.path.basename(f)[:-4]] = c
        prev, n = mosaic_preview(f, c)
        im = Image.open(f).convert("RGB"); W, H = im.size
        orig = im.crop((int(c[0] * W), int(c[1] * H), int(c[2] * W), int(c[3] * H))).resize(prev.size)
        t = Image.new("RGB", (prev.width * 2 + 10, prev.height + 22), "white")
        t.paste(orig, (0, 22)); t.paste(prev, (prev.width + 10, 22))
        ImageDraw.Draw(t).text((3, 4), os.path.basename(f)[6:-4][:40] + f"  ({n})", fill="red")
        tiles.append(t)
    per = 12
    for k in range(0, len(tiles), per):
        grp = tiles[k:k + per]; tw, th = grp[0].size
        sh = Image.new("RGB", (3 * (tw + 12), 4 * (th + 12)), "gray")
        for i, t in enumerate(grp):
            sh.paste(t, ((i % 3) * (tw + 12), (i // 3) * (th + 12)))
        sh.save(f"screen_{k // per + 1}.jpg", quality=82)
    import json; json.dump(crops, open("crops.json", "w"), indent=1)
