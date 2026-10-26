"""A small crossword builder: places as many answers as it can, crossing at shared letters."""
import random


def _fits(grid, w, r, c, dr, dc):
    cross = 0
    for i, ch in enumerate(w):
        y, x = r + dr * i, c + dc * i
        cur = grid.get((y, x))
        if cur is None:
            # a new letter must not touch other letters sideways
            if grid.get((y + dc, x + dr)) or grid.get((y - dc, x - dr)):
                return -1
        elif cur != ch:
            return -1
        else:
            cross += 1
    if grid.get((r - dr, c - dc)) or grid.get((r + dr * len(w), c + dc * len(w))):
        return -1
    return cross


def build(words, tries=300, seed=1):
    rnd = random.Random(seed); best = None
    for _ in range(tries):
        order = sorted(words, key=lambda w: -len(w) + rnd.random() * 3)
        grid = {}; placed = []
        w0 = order[0]
        for i, ch in enumerate(w0): grid[(0, i)] = ch
        placed.append((w0, 0, 0, 0, 1))
        for w in order[1:]:
            opts = []
            for (y, x), ch in list(grid.items()):
                for i, wc in enumerate(w):
                    if wc != ch: continue
                    for dr, dc in ((0, 1), (1, 0)):
                        r, c = y - dr * i, x - dc * i
                        k = _fits(grid, w, r, c, dr, dc)
                        if k > 0: opts.append((k, rnd.random(), r, c, dr, dc))
            if not opts: continue
            k, _, r, c, dr, dc = max(opts)
            for i, ch in enumerate(w): grid[(r + dr * i, c + dc * i)] = ch
            placed.append((w, r, c, dr, dc))
        ys = [y for y, _ in grid]; xs = [x for _, x in grid]
        h, wd = max(ys) - min(ys) + 1, max(xs) - min(xs) + 1
        score = (len(placed), -max(h, wd * 0.9), -h * wd)
        if best is None or score > best[0]:
            best = (score, placed, min(ys), min(xs), h, wd)
    _, placed, y0, x0, h, wd = best
    placed = [(w, r - y0, c - x0, dr, dc) for w, r, c, dr, dc in placed]
    # number the starts, row by row
    starts = sorted({(r, c) for _, r, c, _, _ in placed})
    num = {rc: i + 1 for i, rc in enumerate(starts)}
    entries = [(num[(r, c)], w, r, c, "across" if dc else "down") for w, r, c, dr, dc in placed]
    return entries, h, wd
