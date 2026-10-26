"""Colour plate -> clean colouring page. lineart model + key-ink mask + cleanup."""
import warnings; warnings.filterwarnings("ignore")
import sys, os, cv2, numpy as np
from PIL import Image
from scipy import ndimage as ndi
from controlnet_aux import LineartDetector

_model = None
def model():
    global _model
    if _model is None:
        _model = LineartDetector.from_pretrained("lllyasviel/Annotators")
    return _model

def lineart(path, res=2048, thr=70, min_px=150):
    im = Image.open(path).convert("RGB"); w, h = im.size
    res = int(res * min(w, h) / max(w, h)) // 64 * 64  # the model scales the short side
    raw = model()(im, detect_resolution=res, image_resolution=res)
    g = cv2.resize(np.asarray(raw.convert("L")), (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 1.2)
    lines = g > thr
    # solid key-ink areas (black hats, cats) the model only outlines
    lab = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0] * 100 / 255
    solid = ndi.binary_opening(L < 22, structure=np.ones((5, 5)))
    ink = lines | solid
    lab_, n = ndi.label(ink)
    if n:
        sizes = ndi.sum(ink, lab_, range(1, n + 1))
        keep = np.zeros(n + 1, bool); keep[1:] = sizes >= min_px
        ink = keep[lab_]
    out = np.where(ink, 0, 255).astype(np.uint8)
    out = cv2.GaussianBlur(out, (0, 0), 1.0)
    return np.where(out < 128, 0, 255).astype(np.uint8)

def plate_box(path, pad=12):
    """Bounding box of the printed plate: everything that differs from the
    paper colour, joined up, so margins, stamps and pencil notes fall outside."""
    img = cv2.imread(path)
    small = cv2.resize(img, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = np.concatenate([lab[:8].reshape(-1, 3), lab[-8:].reshape(-1, 3), lab[:, :8].reshape(-1, 3), lab[:, -8:].reshape(-1, 3)])
    paper = np.median(border, axis=0)
    m = np.linalg.norm(lab - paper, axis=-1) > 28
    m = ndi.binary_closing(m, structure=np.ones((15, 15)))
    m = ndi.binary_opening(m, structure=np.ones((9, 9)))
    lab_, n = ndi.label(m)
    big = np.argmax(ndi.sum(m, lab_, range(1, n + 1))) + 1
    ys, xs = np.where(lab_ == big)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = xs.min() * 4, ys.min() * 4, (xs.max() + 1) * 4, (ys.max() + 1) * 4
    return max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)

if __name__ == "__main__":
    outdir = sys.argv[1]; os.makedirs(outdir, exist_ok=True)
    for p in sys.argv[2:]:
        name = os.path.basename(p).replace(".jpg", "")
        dst = os.path.join(outdir, name + "-line.png")
        if os.path.exists(dst): continue
        x0, y0, x1, y1 = plate_box(p)
        color = cv2.imread(p)[y0:y1, x0:x1]
        cpath = os.path.join(outdir, name + "-color.jpg")
        cv2.imwrite(cpath, color, [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(dst, lineart(cpath)); print(name, flush=True)
