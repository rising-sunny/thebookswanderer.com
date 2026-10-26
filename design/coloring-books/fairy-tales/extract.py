import sys, cv2, numpy as np
from scipy import ndimage as ndi

def extract(path):
    bgr = cv2.imread(path)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0] * 100 / 255
    chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    # 1) the black key block: dark and close to neutral
    black = (L < 32) & (chroma < 16)
    # 2) thin dark strokes, also inside coloured areas: black-hat on L
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    hat = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, k)
    strokes = (hat > 22) & (L < 45) & (chroma < 14)
    ink = black | strokes
    ink = ndi.binary_closing(ink, structure=np.ones((2, 2)))
    lab_, n = ndi.label(ink)
    sizes = ndi.sum(ink, lab_, range(1, n + 1))
    keep = np.zeros(n + 1, bool); keep[1:] = sizes >= 120
    ink = keep[lab_]
    out = np.where(ink, 0, 255).astype(np.uint8)
    return bgr, cv2.medianBlur(out, 3)

if __name__ == "__main__":
    for p in sys.argv[1:]:
        bgr, line = extract(p)
        cv2.imwrite(p.replace(".jpg", "-line2.png"), line)
        h, w = line.shape
        pair = np.full((h, w * 2 + 40, 3), 255, np.uint8); pair[:, :w] = bgr; pair[:, w + 40:] = cv2.cvtColor(line, cv2.COLOR_GRAY2BGR)
        s = 1500 / pair.shape[1]; cv2.imwrite(p.replace(".jpg", "-pair2.jpg"), cv2.resize(pair, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
        y, x = int(h * .25), int(w * .35)
        det = np.full((600, 1420, 3), 255, np.uint8); det[:, :700] = bgr[y:y+600, x:x+700]; det[:, 720:] = cv2.cvtColor(line[y:y+600, x:x+700], cv2.COLOR_GRAY2BGR)
        cv2.imwrite(p.replace(".jpg", "-detail2.jpg"), det)
