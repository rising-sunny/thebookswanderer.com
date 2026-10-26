"""Square-grid colour-by-number (mosaic) from a full picture, background included.

The picture is cut to the grid's proportions, each cell takes the average colour
under it, colours are reduced to a small palette of clearly different tones,
lone cells are smoothed into their neighbours, and every cell is numbered.
"""
import numpy as np, cv2
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont
from lowpoly2 import palette, mm2px, DPI

A4 = (210.0, 297.0)
LETTER = (215.9, 279.4)
from lowpoly import FONTS

ART_W, ART_H = 186.0, 198.0      # art box, mm (set per page size in build)


def grid(src, crop, cell_mm):
    im = Image.open(src).convert("RGB"); W0, H0 = im.size
    im = im.crop((int(crop[0] * W0), int(crop[1] * H0), int(crop[2] * W0), int(crop[3] * H0)))
    cols, rows = int(ART_W // cell_mm), int(ART_H // cell_mm)
    # fit the crop to the grid's aspect, centred
    want = cols / rows
    if im.width / im.height > want:
        w = int(im.height * want); im = im.crop(((im.width - w) // 2, 0, (im.width + w) // 2, im.height))
    else:
        h = int(im.width / want); im = im.crop((0, (im.height - h) // 2, im.width, (im.height + h) // 2))
    small = np.asarray(im.resize((cols, rows), Image.BOX))
    return small, cols, rows


def smooth(idx, passes=2):
    """A cell whose four neighbours all disagree with it takes their most common colour."""
    for _ in range(passes):
        out = idx.copy()
        for y in range(idx.shape[0]):
            for x in range(idx.shape[1]):
                nb = [idx[yy, xx] for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
                      if 0 <= yy < idx.shape[0] and 0 <= xx < idx.shape[1]]
                if idx[y, x] not in nb:
                    vals, counts = np.unique(nb, return_counts=True)
                    out[y, x] = vals[np.argmax(counts)]
        idx = out
    return idx


def build(src, crop, out, title, latin, cell_mm=6.0, k=14, merge=7.0, page_size=LETTER):
    global ART_W, ART_H
    PAGE = page_size
    ART_W, ART_H = PAGE[0] - 16, PAGE[1] - 30 - 32
    small, cols, rows = grid(src, crop, cell_mm)
    flat = small.reshape(-1, 3).astype(np.float32)
    idx, pal = palette(flat, np.ones(len(flat)), k, merge)
    idx = smooth(idx.reshape(rows, cols))
    used = np.unique(idx); remap = {u: i for i, u in enumerate(used)}
    pal = pal[used]; idx = np.vectorize(remap.get)(idx)
    # paper white is left blank: no number, nothing to colour
    lab = cv2.cvtColor(pal.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(float)
    paper = (lab[:, 0] * 100 / 255 > 92) & (np.hypot(lab[:, 1] - 128, lab[:, 2] - 128) < 8)
    if paper.any():
        # only paper-coloured cells joined to the edge of the picture are background
        cand = np.isin(idx, np.where(paper)[0])
        lab_, _ = ndi.label(cand)
        edge = np.unique(np.concatenate([lab_[0], lab_[-1], lab_[:, 0], lab_[:, -1]]))
        bg = np.isin(lab_, edge[edge > 0])
        idx = np.where(bg, -1, idx)
        used = np.unique(idx[idx >= 0]); remap = {u: i for i, u in enumerate(used)}
        idx = np.vectorize(lambda v: remap.get(v, -1))(idx); pal = pal[used]
    print(f"{title}: {cols} x {rows} = {cols * rows} squares of {cell_mm} mm, {len(pal)} colours")

    PW, PH = int(mm2px(PAGE[0])), int(mm2px(PAGE[1]))
    c = mm2px(cell_mm)
    x0 = (PW - cols * c) / 2; y0 = mm2px(27) + (mm2px(ART_H) - rows * c) / 2
    serif = lambda s: ImageFont.truetype(f"{FONTS}/Playfair-600.ttf", s)
    italic = lambda s: ImageFont.truetype(f"{FONTS}/Playfair-500i.ttf", s)
    sans = lambda s: ImageFont.truetype(f"{FONTS}/Karla-700.ttf", s)
    pt = lambda v: int(v / 72 * DPI)
    num = sans(pt(min(10, max(6.5, cell_mm * 1.6))))
    pages = []
    for mode in ("solution", "color"):
        page = Image.new("RGB", (PW, PH), "white"); d = ImageDraw.Draw(page)
        d.text((PW / 2, mm2px(14)), title, font=serif(pt(20)), fill=(30, 40, 35), anchor="mm")
        d.text((PW / 2, mm2px(21)), latin, font=italic(pt(10.5)), fill=(110, 110, 105), anchor="mm")
        for y in range(rows):
            for x in range(cols):
                box = (x0 + x * c, y0 + y * c, x0 + (x + 1) * c, y0 + (y + 1) * c)
                if idx[y, x] < 0:
                    continue
                if mode == "solution":
                    d.rectangle(box, fill=tuple(int(v) for v in pal[idx[y, x]]))
                else:
                    d.rectangle(box, outline=(165, 165, 165), width=2)
                    d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), str(idx[y, x] + 1), font=num, fill=(110, 110, 110), anchor="mm")
        n = len(pal); sw = mm2px(9); gap = (mm2px(PAGE[0] - 30) - n * sw) / max(1, n - 1)
        ky = mm2px(PAGE[1] - 30)
        for i, col in enumerate(pal):
            x = mm2px(15) + i * (sw + gap)
            d.rectangle((x, ky, x + sw, ky + sw), fill=tuple(int(v) for v in col), outline=(90, 90, 90), width=3)
            d.text((x + sw / 2, ky + sw + mm2px(4)), str(i + 1), font=sans(pt(11)), fill=(50, 50, 50), anchor="mm")
        note = "The finished picture and its colours" if mode == "solution" else "Colour each square with the colour of its number"
        d.text((PW / 2, mm2px(PAGE[1] - 11)), note, font=italic(pt(9)), fill=(120, 120, 115), anchor="mm")
        page.save(f"{out}-{mode}.png", dpi=(DPI, DPI)); pages.append(page)
    return pages


if __name__ == "__main__":
    A = "after John James Audubon, Birds of America, plate "
    plates = [("plate-431-american-flamingo.jpg", (0.10, 0.17, 0.88, 0.88), "flamingo", "American Flamingo", 431),
              ("plate-351-great-cinereous-owl.jpg", (0.14, 0.15, 0.66, 0.70), "owl", "Great Grey Owl", 351),
              ("plate-211-great-blue-heron.jpg", (0.05, 0.07, 0.90, 0.90), "heron", "Great Blue Heron", 211),
              ("plate-1-wild-turkey.jpg", (0.06, 0.05, 0.96, 0.90), "turkey", "Wild Turkey", 1)]
    pages = []
    for src, crop, out, title, n in plates:
        pages += build(src, crop, f"mos-{out}", title, A + str(n), cell_mm=4.5, page_size=A4)
    pages[0].save("mosaic-sample.pdf", save_all=True, append_images=pages[1:], resolution=DPI)
