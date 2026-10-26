"""The two Audubon mosaic books (11 and 10 plates), solution on the left, grid on the right."""
import glob, sys
import mosaic
from lowpoly2 import DPI

RED = [(431, "American Flamingo", (0.10, 0.17, 0.88, 0.88)),
       (397, "Scarlet Ibis", (0.08, 0.12, 0.80, 0.92)),
       (159, "Northern Cardinal", (0.26, 0.12, 0.82, 0.66)),
       (354, "Scarlet Tanager", (0.36, 0.33, 0.80, 0.75)),
       (44, "Summer Tanager", (0.18, 0.02, 0.70, 0.48)),
       (321, "Roseate Spoonbill", (0.30, 0.14, 0.98, 0.88)),
       (256, "Reddish Egret", (0.30, 0.15, 0.90, 0.90)),
       (322, "Redhead", (0.12, 0.18, 0.86, 0.90)),
       (53, "Painted Bunting", (0.38, 0.48, 0.82, 0.86)),
       (387, "Glossy Ibis", (0.14, 0.22, 0.90, 0.92), True),
       (358, "Pine Grosbeak", (0.12, 0.44, 0.62, 0.80), True)]
BLUE = [(217, "Tricolored Heron", (0.18, 0.13, 0.82, 0.92)),
        (102, "Blue Jay", (0.28, 0.06, 0.88, 0.62)),
        (222, "White Ibis", (0.12, 0.12, 0.84, 0.92)),
        (251, "Brown Pelican", (0.14, 0.08, 0.94, 0.92)),
        (113, "Eastern Bluebird", (0.22, 0.02, 0.72, 0.42)),
        (211, "Great Blue Heron", (0.10, 0.08, 0.90, 0.95)),
        (242, "Snowy Egret", (0.05, 0.08, 0.95, 0.90)),
        (257, "Double-crested Cormorant", (0.02, 0.10, 0.92, 0.80)),
        (216, "Wood Stork", (0.0, 0.03, 1.0, 0.92)),
        (96, "Black-throated Magpie-Jay", (0.12, 0.30, 0.88, 0.92), True)]

if __name__ == "__main__":
    name = sys.argv[1]
    pages = []
    for n, title, crop, *pad in {"red": RED, "blue": BLUE}[name]:
        src = glob.glob(f"aud/plate-{n}-*.jpg")[0]
        pages += mosaic.build(src, crop, f"out/{name}-{n}", title,
                              f"After John James Audubon, Birds of America, plate {n}",
                              cell_mm=float(sys.argv[2]) if len(sys.argv) > 2 else 3.5, page_size=mosaic.A4,
                              pad=bool(pad))
    pages[0].save(f"book-{name}.pdf", save_all=True, append_images=pages[1:], resolution=DPI)
