import cv2, numpy as np
from scipy import ndimage as ndi
def text_boxes(color_path):
    img = cv2.imread(color_path); h, w = img.shape[:2]
    s = 0.25; small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0] * 100 / 255; C = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    pale = (L > 72) & (C < 40)
    # glyphs are dark specks inside pale panels: close them in
    m = ndi.binary_closing(pale, structure=np.ones((7, 7)))
    m = ndi.binary_opening(m, structure=np.ones((5, 5)))
    lab_, n = ndi.label(m); boxes = []
    for i, sl in enumerate(ndi.find_objects(lab_), 1):
        ys, xs = sl; bh, bw = ys.stop - ys.start, xs.stop - xs.start
        area = (lab_[sl] == i).sum()
        if bh * bw < 0.02 * m.size or area / (bh * bw) < 0.80: continue
        # must actually hold text: many small dark specks inside
        inner = ~pale[sl] & (lab_[sl] == 0) | (~pale[sl])
        dark = (L[sl] < 45).mean()
        if dark < 0.02: continue
        boxes.append((int(xs.start / s), int(ys.start / s), int(xs.stop / s), int(ys.stop / s)))
    return boxes
if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]: print(p, text_boxes(p))
