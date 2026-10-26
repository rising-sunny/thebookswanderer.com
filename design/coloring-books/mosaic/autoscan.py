"""Score every plate for the mosaic: the biggest strongly coloured, non-foliage
shape (the bird) and how much it stands out from what surrounds it."""
import glob, os, json
from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
import numpy as np, cv2
from scipy import ndimage as ndi
from PIL import Image, ImageDraw

def analyse(path):
    a = np.asarray(Image.open(path).convert("RGB"))
    h, w = a.shape[:2]
    a = a[int(h * .06):int(h * .89)]                      # skip plate lettering
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV).astype(int)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    foliage = (H > 25) & (H < 85)
    bird = (S > 95) & (V > 50) & ~foliage
    bird = ndi.binary_opening(ndi.binary_closing(bird, np.ones((7, 7))), np.ones((3, 3)))
    lab_, n = ndi.label(bird)
    if not n:
        return None
    sizes = ndi.sum(bird, lab_, range(1, n + 1))
    k = int(np.argmax(sizes)) + 1; big = lab_ == k
    frac = sizes[k - 1] / bird.size
    ys, xs = np.where(big)
    hue = np.median(H[big])
    # contrast: bird colour vs a ring around its bounding box
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(float)
    ring = ndi.binary_dilation(big, iterations=15) & ~ndi.binary_dilation(big, iterations=4)
    contrast = np.linalg.norm(lab[big].mean(0) - lab[ring].mean(0))
    off = int(h * .06)
    box = (xs.min() / w, (ys.min() + off) / h, xs.max() / w, (ys.max() + off) / h)
    return dict(frac=float(frac), contrast=float(contrast), hue=float(hue), box=box)


if __name__ == "__main__":
    res = {}
    for f in sorted(glob.glob("aud_s/*.jpg")):
        r = analyse(f)
        if r: res[os.path.basename(f)[6:-4]] = r
    for r in res.values():
        r["score"] = min(r["frac"], 0.25) * 4 * min(r["contrast"], 60) / 60
    json.dump(res, open("autoscan.json", "w"), indent=1)
    top = sorted(res.items(), key=lambda kv: -kv[1]["score"])[:60]
    for n, r in top:
        print(f"{r['score']:.2f} frac {r['frac']:.3f} contrast {r['contrast']:.0f} hue {r['hue']:.0f}  {n}")
