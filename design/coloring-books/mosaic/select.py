import json
from PIL import Image, ImageDraw
from screen import mosaic_preview
CROPS = {
 "431-american-flamingo": (0.10, 0.17, 0.88, 0.88),
 "397-scarlet-ibis": (0.08, 0.12, 0.8, 0.92),
 "159-cardinal-grosbeak": (0.26, 0.12, 0.82, 0.66),
 "217-louisiana-heron": (0.18, 0.13, 0.82, 0.92),
 "256-purple-heron": (0.3, 0.15, 0.9, 0.9),
 "222-white-ibis": (0.12, 0.12, 0.84, 0.92),
 "357-american-magpie": (0.24, 0.06, 0.94, 0.7),
 "354-louisiana-tanager": (0.36, 0.33, 0.8, 0.75),
 "53-painted-finch": (0.38, 0.48, 0.82, 0.86),
 "102-blue-jay": (0.28, 0.06, 0.88, 0.62),
 "77-belted-kingfisher": (0.36, 0.02, 0.96, 0.55),
 "321-roseate-spoonbill": (0.3, 0.14, 0.98, 0.88),
 "251-brown-pelican": (0.14, 0.08, 0.94, 0.92),
 "322-red-headed-duck": (0.12, 0.18, 0.86, 0.9),
 "387-glossy-ibis": (0.14, 0.22, 0.9, 0.92),
 "44-summer-red-bird": (0.18, 0.02, 0.7, 0.48),
}
if __name__ == "__main__":
    from screen import COLS, ROWS
    def fit(path, c):
        """Grow the crop (never cut it) to the grid's proportions."""
        W, H = Image.open(path).size
        x0, y0, x1, y1 = c; want = COLS / ROWS * H / W
        if (x1 - x0) / (y1 - y0) < want:
            d = (want * (y1 - y0) - (x1 - x0)) / 2; x0 -= d; x1 += d
        else:
            d = ((x1 - x0) / want - (y1 - y0)) / 2; y0 -= d; y1 += d
        sx = max(0, -x0) - max(0, x1 - 1); sy = max(0, -y0) - max(0, y1 - 1)
        return (x0 + sx, y0 + sy, x1 + sx, y1 + sy)
    tiles = []
    for n, c in CROPS.items():
        prev, k = mosaic_preview(f"aud/plate-{n}.jpg", c, px=6)
        t = Image.new("RGB", (prev.width, prev.height + 20), "white"); t.paste(prev, (0, 20))
        ImageDraw.Draw(t).text((3, 4), n, fill="red"); tiles.append(t)
    tw, th = tiles[0].size
    sh = Image.new("RGB", (8 * (tw + 8), 2 * (th + 8)), "gray")
    for i, t in enumerate(tiles): sh.paste(t, ((i % 8) * (tw + 8), (i // 8) * (th + 8)))
    sh.save("select.jpg", quality=85)
    json.dump(CROPS, open("crops_sel.json", "w"), indent=1)
