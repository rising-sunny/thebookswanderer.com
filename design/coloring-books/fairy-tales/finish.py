"""Trim, blank the verse boxes in the line art, thicken lines. Writes final/."""
import os, cv2, numpy as np
from scipy import ndimage as ndi
# name: (top trim fraction, [text regions as x0,y0,x1,y1 fractions])
PLATES = {
 "sleepingbeauty00cran-n1": (0, [(.08, .86, .92, .99)]),
 "sleepingbeauty00cran-n2": (.075, [(.10, .87, .87, .985)]),
 "sleepingbeauty00cran-n3": (0, [(.11, .865, .88, .985)]),
 "sleepingbeauty00cran-n8": (0, [(.10, .875, .86, .985)]),
 "sleepingbeauty00cran-n9": (0, [(.11, .87, .87, .985)]),
 "Beautybeast00CranA-n6": (0, []),
 "Beautybeast00CranA-n11": (0, []),
 "Beautybeast00CranA-n12": (0, []),
 "frogprince00CranA-n6": (0, []),
 "frogprince00CranA-n11": (0, []),
 "frogprince00CranA-n12": (0, []),
 "Bluebeard00Cran-n2": (.07, [(.08, .70, .53, .975)]),
 "Bluebeard00Cran-n5": (0, [(.04, .02, .55, .29)]),
 "Bluebeard00Cran-n7": (0, [(.04, .70, .60, .985)]),
 "Bluebeard00Cran-n10": (0, [(.54, .02, .98, .42)]),
 "LittleRedRiding00Cran-n1": (0, [(.02, .01, .98, .115)]),
 "LittleRedRiding00Cran-n5": (0, [(.06, .01, .94, .17)]),
 "LittleRedRiding00Cran-n13": (0, [(.03, .015, .97, .15)]),
 "LittleRedRiding00Cran-n14": (0, [(.04, .015, .96, .165)]),
 "GoodyTwoShoes00CranA-n2": (.02, []),
 "GoodyTwoShoes00CranA-n6": (0, []),
 "GoodyTwoShoes00CranA-n11": (0, []),
 "hindwood00Cran-n2": (.02, []),
 "yellowdwarf00Cran-n12": (0, []),
}
os.makedirs("final", exist_ok=True)
for name, (top, regions) in PLATES.items():
    color = cv2.imread(f"out/{name}-color.jpg"); line = cv2.imread(f"out/{name}-line.png", 0)
    h0 = color.shape[0]; t = int(h0 * top)
    color, line = color[t:], line[t:]
    h, w = line.shape
    ink = line < 128
    lab, n = ndi.label(ink)
    objs = ndi.find_objects(lab)
    for (x0, y0, x1, y1) in regions:
        X0, Y0, X1, Y1 = int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)
        for i, sl in enumerate(objs, 1):
            if sl is None: continue
            ys, xs = sl
            # letters and stray marks: small, wholly inside the box
            if ys.start >= Y0 and ys.stop <= Y1 and xs.start >= X0 and xs.stop <= X1 \
               and (ys.stop - ys.start) < 0.05 * h and (xs.stop - xs.start) < 0.12 * w:
                ink[sl][lab[sl] == i] = False
    out = np.where(ink, 0, 255).astype(np.uint8)
    out = cv2.erode(out, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4)))
    cv2.imwrite(f"final/{name}-line.png", out)
    cv2.imwrite(f"final/{name}-color.jpg", color, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(name, w, h)
