"""Editorial reels and saveable stills built from the shop's own images."""

import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

S = Path(__file__).resolve().parents[1] / "social"
W, H, FPS = 720, 1280, 30
PAPER = "#F6F0DF"
INK = "#1F3029"
GREEN = "#234D40"
OX = "#873A32"
OCHRE = "#DBB76A"
SLATE = "#244F61"
MUTED = "#516559"
PALETTE = [
    (OX, "Rose", "Under", "200 pages"),
    (GREEN, "Fern", "Has a map", "inside"),
    (SLATE, "Ink", "A friend’s", "recommendation"),
]
TRACKS = {
    "challenge": "reading-room",
    "wonderland": "disappearing-ink",
    "object": "walnut",
}
DURATION = {"challenge": 15.4, "wonderland": 15.4, "object": 12.8}
HOLDER = "wooden-finger-book-holder"


@lru_cache(maxsize=100)
def face(size, kind="sans"):
    names = {
        "sans": "Karla-400.ttf",
        "bold": "Karla-700.ttf",
        "serif": "Playfair-600.ttf",
        "italic": "Playfair-500i.ttf",
    }
    return ImageFont.truetype(str(S / "fonts" / names[kind]), size)


def word(draw, xy, text, size, color=INK, kind="sans", anchor="lt"):
    draw.text(xy, text, font=face(size, kind), fill=color, anchor=anchor)


def lines(draw, xy, text, width, size, color=INK, kind="serif", limit=3):
    for fs in range(size, 24, -2):
        f = face(fs, kind)
        rows = []
        line = ""
        for token in text.split():
            nxt = (line + " " + token).strip()
            if line and draw.textlength(nxt, font=f) > width:
                rows.append(line)
                line = token
            else:
                line = nxt
        if line:
            rows.append(line)
        if len(rows) <= limit:
            break
    for k, row in enumerate(rows[:limit]):
        word(draw, (xy[0], xy[1] + k * (fs + 12)), row, fs, color, kind)
    return xy[1] + len(rows[:limit]) * (fs + 12)


def smooth(v):
    v = max(0, min(1, v))
    return v * v * (3 - 2 * v)


def panel(photo, size, scale=1, center=(0.5, 0.5)):
    # Center coordinates refer to the source, so that motion can follow a detail.
    w, h = size
    a, b = photo.size
    factor = min(a / w, b / h) / scale
    dw, dh = w * factor, h * factor
    x = max(0, min(a - dw, a * center[0] - dw / 2))
    y = max(0, min(b - dh, b * center[1] - dh / 2))
    return photo.resize((w, h), Image.Resampling.BICUBIC, box=(x, y, x + dw, y + dh))


def top(d, tone=INK):
    word(d, (52, 108), "THE BOOKS WANDERER", 21, tone, "bold")
    d.line((52, 151, 657, 151), fill=tone, width=2)


def footer(d, label, color=INK):
    d.line((52, 1083, 645, 1083), fill=color, width=2)
    word(d, (52, 1105), label, 23, color, "bold")


def spines(im, y, t):
    d = ImageDraw.Draw(im)
    for i, (clr, name, *_) in enumerate(PALETTE):
        x = 56 + i * 195
        dy = int((1 - smooth((t + i * 0.08) / 0.65)) * 32)
        y0 = y + dy + [28, 0, 17][i]
        d.rounded_rectangle((x, y0, x + 175, y0 + 244), radius=7, fill=clr)
        for v in [19, 25, 212, 218]:
            d.line((x + 12, y0 + v, x + 163, y0 + v), fill="#E7D9AF", width=1)
        word(d, (x + 88, y0 + 80), name, 38, PAPER, "italic", "mt")
        d.ellipse((x + 78, y0 + 155, x + 96, y0 + 173), outline=PAPER, width=2)


def palette(p):
    prompts = p.get("trial", {}).get("prompts")
    if not prompts:
        return PALETTE
    return [
        (color, name, *prompt)
        for (color, name, *_), prompt in zip(PALETTE, prompts, strict=True)
    ]


def challenge(t, choices):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    top(d)
    beat = 60 / 108
    start = 8 * beat
    end = 20 * beat
    if t < start:
        word(d, (53, 233), "Pick a spine.", 79, INK, "serif")
        word(d, (54, 333), "Find your next read.", 48, INK, "italic")
        spines(im, 504, t)
        choice_seconds = max(1, 3 - int(max(0, t - beat) / (2 * beat)))
        word(d, (55, 923), "Choose before the reveal", 30, INK)
        for k in range(3):
            x = 55 + k * 63
            d.rounded_rectangle(
                (x, 994, x + 47, 1002),
                radius=4,
                fill=GREEN if k < choice_seconds else "#C4C4B4",
            )
        footer(d, "The 2027 Reading Challenge")
    elif t < end:
        i = min(2, int((t - start) / (4 * beat)))
        local = (t - start) - i * 4 * beat
        clr, name, one, two = choices[i]
        d.rectangle((0, 0, W, H), fill=clr)
        top(d, PAPER)
        word(d, (54, 238), "You picked " + name + ".", 39, PAPER, "italic")
        y = 440 + int(22 * (1 - smooth(local / 0.28)))
        word(d, (49, y), one, 77, PAPER, "serif")
        lines(d, (49, y + 107), two, 615, 72, PAPER, "serif", 2)
        for n in range(3):
            x = 55 + n * 78
            d.line((x, 855, x + 57, 855), fill=PAPER if n <= i else "#A69985", width=5)
        footer(d, "One prompt for your next book", PAPER)
    else:
        word(d, (50, 226), "Your next read", 65, INK, "serif")
        for i, (clr, name, a, b) in enumerate(choices):
            y = 413 + i * 126
            d.rounded_rectangle((52, y, 72, y + 68), radius=4, fill=clr)
            word(d, (97, y + 1), name, 23, MUTED, "bold")
            word(d, (97, y + 32), a + " " + b, 34, INK, "serif")
        footer(d, "Find all 52 free prompts on our site")
    return im


def wonderland(t, art, hatter):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    top(d)
    beat = 60 / 84
    if t < 6 * beat:
        word(
            d,
            (51, 216),
            "Whose hat is that?" if hatter else "Know that grin?",
            65,
            INK,
            "serif",
        )
        word(d, (54, 326), "One clue from Wonderland.", 33, OX, "italic")
        # The mouth is at (0.49, 0.31) of the original Tenniel plate.
        im.paste(
            panel(
                art,
                (624, 402),
                4.7 - 0.75 * smooth(t / (6 * beat)),
                (0.43, 0.22) if hatter else (0.49, 0.32),
            ),
            (48, 486),
        )
        ImageDraw.Draw(im).rectangle((48, 486, 671, 887), outline=INK, width=2)
        footer(d, "Look closely before the reveal")
    elif t < 15 * beat:
        word(
            d,
            (52, 200),
            "The Mad Hatter." if hatter else "The Cheshire Cat.",
            62,
            INK,
            "serif",
        )
        y = 338
        im.paste(
            panel(
                art,
                (614, 610),
                1.52 - 0.52 * smooth((t - 6 * beat) / (8 * beat)),
                (0.505, 0.40),
            ),
            (52, y),
        )
        d.rectangle((52, y, 665, y + 610), outline=INK, width=2)
        footer(d, "Illustration by John Tenniel")
    else:
        word(d, (50, 203), "Your turn", 60, INK, "serif")
        word(d, (51, 286), "to colour it.", 63, OX, "italic")
        page = ImageOps.contain(art, (410, 496))
        im.paste(page, ((W - page.width) // 2, 433))
        footer(d, "Three free printable colouring pages")
    return im


def product_info(p):
    if p.get("trial", {}).get("shots"):
        return p["trial"]["shots"]
    if p["slug"] == HOLDER:
        return [
            "One hand for coffee?",
            "Slip your thumb through.",
            "The wings hold the pages open.",
            "Wooden finger book holder",
        ]
    name = p["title"].split(" | ")[0].split(" — ")[0].split(",")[0]
    description = (
        " ".join((p.get("description") or "").split())
        .split(". ")[0]
        .strip()
        .rstrip(".")
    )
    detail = description + "." if description and len(description) < 90 else name
    return [name, detail, "Take a closer look.", name]


def object_frame(t, p, images):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    bar = 4 * 60 / 103
    idx = 0 if t < bar else 1 if t < bar * 2 else 2 if t < bar * 4 else 3
    start = [0, bar, bar * 2, bar * 4][idx]
    duration = [bar, bar, bar * 2, DURATION["object"] - bar * 4][idx]
    prog = smooth((t - start) / duration)
    text = product_info(p)
    if idx < 3:
        order = [1, 0, 2] if p["slug"] == HOLDER else [0, 1, 2]
        im.paste(
            panel(images[order[idx] % len(images)], (W, 755), 1.03 + 0.075 * prog),
            (0, 0),
        )
        d.rectangle((0, 752, W, 765), fill=OCHRE)
        d.rectangle((45, 93, 309, 142), fill=PAPER)
        word(d, (59, 107), "THE BOOKS WANDERER", 20, INK, "bold")
        lines(d, (48, 835), text[idx], 590, 65, INK, "serif", 3)
    else:
        top(d)
        lines(d, (48, 208), text[3], 620, 64, INK, "serif", 3)
        im.paste(panel(images[0], (590, 442), 1.03), (55, 527))
        if p.get("price_usd") is not None:
            lo = p["price_usd"]
            prefix = "From " if (p.get("price_max_usd") or lo) > lo else ""
            footer(d, f"{prefix}${lo:.2f} USD  ·  Details on our site")
    return im


def edition(p):
    return {
        "content/reading-challenge-2027": "challenge",
        "content/free-literary-coloring-pages": "wonderland",
    }.get(p["slug"], "object")


def illustration(hatter):
    name = (
        "free-literary-coloring-pages-3.jpg"
        if hatter
        else "free-literary-coloring-pages-1.jpg"
    )
    with Image.open(S / "content" / name) as source:
        return source.convert("RGB")


def render(story, p, images, out):
    hatter = p.get("trial", {}).get("illustration") == "hatter"
    choices = palette(p)
    art = illustration(hatter) if story == "wonderland" else None
    track = S / "story-music" / (TRACKS[story] + ".m4a")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-i",
        str(track),
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-threads",
        "2",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-t",
        str(DURATION[story]),
        "-movflags",
        "+faststart",
        str(out),
    ]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as ff:
        try:
            for i in range(round(FPS * DURATION[story])):
                t = i / FPS
                if story == "challenge":
                    frame = challenge(t, choices)
                elif story == "wonderland":
                    frame = wonderland(t, art, hatter)
                else:
                    frame = object_frame(t, p, images)
                ff.stdin.write(frame.tobytes())
        finally:
            ff.stdin.close()
        if ff.wait():
            raise RuntimeError("The story encoder failed")


def pin(story, p, images, out):
    w, h = 1000, 1500
    im = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(im)

    def mark():
        word(d, (68, 63), "THE BOOKS WANDERER", 27, INK, "bold")
        d.line((67, 119, 925, 119), fill=INK, width=2)

    mark()
    if story == "challenge":
        word(d, (65, 209), "Three ways to pick", 73, INK, "serif")
        word(d, (65, 313), "your next read", 80, GREEN, "italic")
        for i, (clr, n, a, b) in enumerate(palette(p)):
            y = 548 + i * 206
            d.rounded_rectangle((67, y, 153, y + 151), radius=8, fill=clr)
            d.line((79, y + 18, 141, y + 18), fill=PAPER, width=2)
            d.line((79, y + 131, 141, y + 131), fill=PAPER, width=2)
            word(d, (194, y + 14), n, 27, MUTED, "bold")
            lines(d, (193, y + 61), a + " " + b, 700, 49, INK, "serif", 2)
        bottom = "Get the free 52-prompt reading challenge"
    elif story == "wonderland":
        im.paste(OX, (0, 0, w, h))
        d = ImageDraw.Draw(im)
        word(d, (64, 72), "THE BOOKS WANDERER", 26, PAPER, "bold")
        hatter = p.get("trial", {}).get("illustration") == "hatter"
        a = illustration(hatter)
        plate = a.crop((94, 94, 911, 1097))
        art = ImageOps.contain(plate, (764, 805))
        x = (w - art.width) // 2
        y = 151
        d.rectangle(
            (x - 14, y - 14, x + art.width + 14, y + art.height + 14), fill=PAPER
        )
        im.paste(art, (x, y))
        word(d, (66, 1026), "Colour the", 62, PAPER, "serif")
        word(
            d,
            (65, 1106),
            "Mad Hatter" if hatter else "Cheshire Cat",
            89,
            PAPER,
            "italic",
        )
        d.line((68, 1289, 924, 1289), fill="#D7AC87", width=2)
        word(
            d,
            (67, 1333),
            "Three literary colouring pages · Free PDF",
            35,
            PAPER,
            "bold",
        )
        word(d, (67, 1411), "thebookswanderer.com", 24, PAPER)
        im.save(out, quality=94, optimize=True)
        return
    else:
        im.paste(panel(images[min(1, len(images) - 1)], (1000, 965)), (0, 0))
        d.rectangle((0, 963, w, h), fill=GREEN)
        d.rectangle((57, 59, 406, 126), fill=PAPER)
        word(d, (76, 81), "THE BOOKS WANDERER", 27, INK, "bold")
        label = "One-handed reading" if p["slug"] == HOLDER else product_info(p)[3]
        end = lines(d, (59, 1025), label, 884, 66, PAPER, "serif", 2)
        detail = (
            "Slide your thumb through and rest the wings across the pages."
            if p["slug"] == HOLDER
            else product_info(p)[1]
        )
        lines(d, (63, end + 35), detail, 856, 37, PAPER, "sans", 2)
        d.line((65, 1360, 930, 1360), fill="#ABBAA3", width=2)
        word(d, (63, 1407), "thebookswanderer.com", 25, PAPER, "bold")
        im.save(out, quality=94, optimize=True)
        return
    d.line((68, 1341, 930, 1341), fill=INK, width=2)
    word(d, (68, 1370), bottom, 33, INK, "bold")
    word(d, (68, 1431), "thebookswanderer.com", 23, MUTED)
    im.save(out, quality=94, optimize=True)


def captions(story, p, base):
    if p.get("trial", {}).get("illustration") == "hatter":
        opening = "Can you name the guest at the tea party just from his hat? Find John Tenniel’s illustration in our free printable set."
        action = "Get the printable pages"
    elif p.get("trial", {}).get("prompts"):
        opening = "A winter setting, a book in letters, or a second-hand find. Which reading prompt would you pick?"
        action = "Find all 52 prompts"
    elif story == "challenge":
        opening = "Rose, fern or ink? Pick a spine before the prompts appear. Which book would you put beside yours?"
        action = "Find all 52 prompts"
    elif story == "wonderland":
        opening = "Could you name the character from the grin alone? This John Tenniel illustration is one of our three free literary colouring pages."
        action = "Get the printable pages"
    elif p["slug"] == HOLDER:
        opening = "Coffee in one hand, a paperback in the other. Slide your thumb through the wooden holder and rest its wings across the open pages."
        action = "See the wooden holder"
    else:
        label, detail, _, _ = product_info(p)
        opening = label if label == detail else f"{label}. {detail}"
        action = "See the details"
    path = p.get("url") or "/products/" + p["slug"]
    link = (
        base
        + path
        + "?utm_source=facebook&utm_medium=social&utm_campaign=reader_stories&utm_content="
        + story
    )
    if p.get("trial_date"):
        link = f"{base}{path}?utm_source=facebook&utm_medium=social&utm_campaign=reader_stories_14d&utm_content={p['trial_date']}-{story}"
    return (
        opening + "\n\n" + action + " → " + link,
        opening + "\n\n" + action + " via the link in our bio. #Bookstagram",
    )
