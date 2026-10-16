#!/usr/bin/env python3
"""
Daily product reel for the Facebook Page and Instagram.

Picks the product that has gone longest without a post, renders a 16.5 s
vertical reel (photos, brand type, one of three original waltzes in
server/social/music), and publishes it as a Facebook Reel with a link to the
product and an Instagram Reel that points to the link in bio. On Pinterest
the same reel goes up as a video pin, with SOCIAL_PINTEREST_IMAGE_PINS (2)
image pins rotating through the product's other photos and designs.

  python scripts/daily_social_post.py --dry-run            # render + captions, no posting
  python scripts/daily_social_post.py --slug some-product  # force a product
  python scripts/daily_social_post.py --at-hour 11         # cron guard (see below)

Cron runs it at 15:03 and 16:03 UTC; --at-hour 11 lets only the run that
falls at 11:xx in New York go through, so the post keeps its local time
across daylight-saving changes. A second run on the same day is a no-op.

SOCIAL_POST_ENABLED=0 in server/.env pauses it without touching cron.
Needs FB_PAGE_ID / FB_PAGE_TOKEN (Page token with pages_manage_posts and
instagram_content_publish) and ffmpeg. Products come from the public API.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

SOCIAL = ROOT / "social"
STATE = Path(os.getenv("SOCIAL_POST_STATE", ROOT / "data" / "social_posts.json"))
BASE = (os.getenv("PUBLIC_BASE_URL") or "https://thebookswanderer.com").rstrip("/")
GRAPH = "https://graph.facebook.com/v21.0"
RUPLOAD = "https://rupload.facebook.com"
NY = ZoneInfo("America/New_York")

W, H, FPS, DUR = 1080, 1920, 30, 16.5
SCENE = 3.0           # one scene per two bars of the 3/4 waltz at 120 bpm
END_START = 12.0
XFADE = 0.45
GREEN_900 = (16, 36, 26)
CREAM = (248, 242, 229)
CREAM_50 = (253, 250, 243)
GOLD_300 = (226, 196, 124)
GOLD_600 = (169, 124, 34)
RED_700 = (139, 47, 39)
INK = (36, 41, 31)
TITLE_GREEN = (27, 55, 40)

HASHTAGS = {
    "book-accessories": "#bookaccessories #bookmarks #booklover #bookish #readingtime #bookstagram",
    "decor": "#readingnook #bookshelfdecor #booklover #bookish #cozyreading #bookstagram",
    "ereader-accessories": "#kindle #kindleaccessories #ereader #booklover #bookish #bookstagram",
    "printables": "#readingjournal #printable #booktracker #booklover #bookish #bookstagram",
}
DEFAULT_TAGS = "#booklover #bookish #readingtime #bookstagram"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(SOCIAL / "fonts" / name), size)


# ── product choice ────────────────────────────────────────────────────────

def load_state() -> list[dict]:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return []


def save_state(entries: list[dict]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(entries[-500:], indent=1))


def pick_product(client: httpx.Client, state: list[dict], slug: str | None) -> dict:
    products = client.get(f"{BASE}/api/products").json()["products"]
    if slug:
        pool = [p for p in products if p["slug"] == slug]
        if not pool:
            raise SystemExit(f"no active product {slug}")
    else:
        last = {}
        for e in state:
            last[e["slug"]] = e["date"]
        # never posted first, then the longest wait; ties broken by newest product
        pool = sorted(products, key=lambda p: (last.get(p["slug"], ""), -p["id"]))[:1]
    return client.get(f"{BASE}/api/products/by-slug/{pool[0]['slug']}").json()


def abs_url(u: str) -> str:
    return u if u.startswith("http") else f"{BASE}/{u.lstrip('/')}"


def product_images(client: httpx.Client, p: dict) -> list[Image.Image]:
    urls: list[str] = []
    variant_imgs = [v.get("image_url") for v in p.get("variants") or []]
    for u in [p.get("image_url"), *(p.get("lifestyle_images") or []), *variant_imgs]:
        if u and u not in urls:
            urls.append(u)
    out = []
    for u in urls[:6]:
        try:
            r = client.get(abs_url(u), timeout=40)
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if min(im.size) >= 500:
                out.append(im)
        except Exception:  # noqa: BLE001
            continue
        if len(out) == 4:
            break
    if not out:
        raise SystemExit(f"{p['slug']}: no usable images")
    while len(out) < 4:  # reuse with a different crop/drift
        out.append(out[len(out) % len(out)])
    return out


# ── copy ──────────────────────────────────────────────────────────────────

def money(v: float) -> str:
    return f"${v:.2f}"


def price_line(p: dict) -> str:
    lo, hi = p["price_usd"], p.get("price_max_usd") or p["price_usd"]
    return f"from {money(lo)}" if hi > lo else money(lo)


def us_only(p: dict) -> bool:
    return (p.get("supplier") or "cj") == "printify"


def shipping_line(p: dict) -> str:
    if p.get("supplier") == "digital":
        return "Instant download"
    if p.get("supplier") == "lulu":
        return "Printed to order · see delivery countries"
    return "Printed to order · ships within the US" if us_only(p) else "Free shipping worldwide"


def category_line(slug: str) -> str:
    try:
        from services import categories

        for c in categories.CATEGORIES:
            if c["slug"] == slug:
                return c["description"]
    except Exception:  # noqa: BLE001
        pass
    return "Small things for long reading hours."


def captions(p: dict) -> tuple[str, str]:
    tags = HASHTAGS.get(p.get("category_slug") or "", DEFAULT_TAGS)
    price = price_line(p)
    head = f"{p['title']}\n\n{(p.get('description') or '').strip()}\n\n{price[0].upper() + price[1:]} · {shipping_line(p)}"
    link = f"{BASE}/products/{p['slug']}?utm_source=facebook&utm_medium=social&utm_campaign=daily_reel"
    fb = f"{head}\n\n{link}\n\n{tags}"
    ig = f"{head}\n\nLink in bio → thebookswanderer.com\n\n{tags}"
    return fb, ig


# ── video ─────────────────────────────────────────────────────────────────

def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def background(color, grain=10, vignette=0.32, seed=1) -> Image.Image:
    random.seed(seed)
    base = Image.new("RGB", (W, H), color)
    noise = Image.effect_noise((W, H), grain).convert("L")
    base = Image.blend(base, Image.merge("RGB", [noise] * 3), 0.035)
    grad = Image.radial_gradient("L").resize((int(W * 1.6), int(H * 1.5)))
    grad = grad.crop(((grad.width - W) // 2, int(grad.height * 0.05), (grad.width + W) // 2, int(grad.height * 0.05) + H))
    shade = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(shade, base, grad.point(lambda v: int(v * vignette)))


def wrap(draw, text, fnt, width, max_lines=2):
    words, lines, line = text.split(), [], ""
    for w in words:
        t = (line + " " + w).strip()
        if draw.textlength(t, font=fnt) <= width:
            line = t
        else:
            lines.append(line)
            line = w
    lines.append(line)
    return lines if len(lines) <= max_lines else None


def fit_lines(draw, text, name, size, width, max_lines=2, min_size=52):
    while size >= min_size:
        f = font(name, size)
        lines = wrap(draw, text, f, width, max_lines)
        if lines:
            return f, lines
        size -= 4
    f = font(name, min_size)
    return f, wrap(draw, text, f, width, 99)[:max_lines]


class Reel:
    CARD_W, CARD_H, CARD_Y = 900, 940, 250
    TEXT_X, EYEBROW_Y, HEAD_Y = 90, 1255, 1310

    def __init__(self, p: dict, images: list[Image.Image], seed: int):
        self.p = p
        self.rng = random.Random(seed)
        self.bg_dark = background(GREEN_900, seed=seed)
        self.bg_cream = background(CREAM, grain=6, vignette=0.1, seed=seed + 1)
        self.card_x = (W - self.CARD_W) // 2
        self.mask = Image.new("L", (self.CARD_W, self.CARD_H), 0)
        ImageDraw.Draw(self.mask).rounded_rectangle([0, 0, self.CARD_W - 1, self.CARD_H - 1], radius=14, fill=255)
        sh = Image.new("L", (self.CARD_W + 120, self.CARD_H + 120), 0)
        ImageDraw.Draw(sh).rounded_rectangle([60, 80, self.CARD_W + 60, self.CARD_H + 60], radius=20, fill=150)
        self.shadow = sh.filter(ImageFilter.GaussianBlur(28))
        n = len(p.get("variants") or [])
        scene_copy = [
            ((p.get("category") or "The Books Wanderer").upper(), p["title"]),
            ("CHOSEN ONE BY ONE", f"{n} designs to choose from" if n > 1 else "Kept few on purpose"),
            ("SHIPPING", shipping_line(p)),
            ("FOR READERS", category_line(p.get("category_slug") or "")),
        ]
        order = [0, 1, 2, 3]
        tail = order[1:]
        self.rng.shuffle(tail)  # vary the middle of the reel from post to post
        self.scenes = [(i * SCENE, images[i], *scene_copy[k]) for i, k in enumerate([0, *tail])]
        self.drift = [self.rng.choice((-1, 1)) for _ in range(4)]
        self.hero = images[0]

    def kenburns(self, img, prog, k):
        iw, ih = img.size
        ar = self.CARD_W / self.CARD_H
        bw, bh = (ih * ar, ih) if iw / ih > ar else (iw, iw / ar)
        z = 1 + 0.08 * prog
        cw, ch = bw / z, bh / z
        dx = (iw - cw) * (0.5 + 0.12 * self.drift[k] * (prog - 0.5))
        dy = (ih - ch) * (0.45 + 0.08 * (prog - 0.5))
        crop = img.crop((dx, dy, dx + cw, dy + ch)).resize((self.CARD_W, self.CARD_H), Image.LANCZOS)
        return crop.filter(ImageFilter.UnsharpMask(radius=1.2, percent=50, threshold=2))

    def text(self, eyebrow, headline, t_in, t):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        a1 = ease((t - t_in) / 0.45)
        if a1 > 0:
            y = self.EYEBROW_Y + 20 * (1 - a1)
            d.line([(self.TEXT_X, y + 17), (self.TEXT_X + 44, y + 17)], fill=GOLD_300 + (int(255 * a1),), width=2)
            x = self.TEXT_X + 62
            ef = font("Karla-700.ttf", 30)
            for ch in eyebrow[:34]:
                d.text((x, y), ch, font=ef, fill=GOLD_300 + (int(255 * a1),))
                x += d.textlength(ch, font=ef) + 6
        hf, lines = fit_lines(d, headline, "Playfair-500i.ttf", 92, W - 2 * self.TEXT_X - 60)
        for k, line in enumerate(lines):
            a = ease((t - t_in - 0.18 - 0.12 * k) / 0.5)
            if a > 0:
                y = self.HEAD_Y + int(hf.size * 1.2) * k + 26 * (1 - a)
                d.text((self.TEXT_X - 4, y), line, font=hf, fill=CREAM_50 + (int(255 * a),))
        return lay

    def scene(self, idx, t):
        start, img, eyebrow, headline = self.scenes[idx]
        prog = (t - start) / (SCENE + XFADE)
        f = self.bg_dark.copy()
        f.paste((0, 0, 0), (self.card_x - 60, self.CARD_Y - 60), self.shadow)
        f.paste(self.kenburns(img, prog, idx), (self.card_x, self.CARD_Y), self.mask)
        f = f.convert("RGBA")
        f.alpha_composite(self.text(eyebrow, headline, start + 0.15, t))
        return f.convert("RGB")

    def end(self, t):
        p = t - END_START
        f = self.bg_cream.copy().convert("RGBA")
        a0 = ease(p / 0.6)
        size = int(560 + 30 * (1 - a0))
        ph = ImageOps.fit(self.hero, (size, size), Image.LANCZOS)
        card = Image.new("RGBA", (size + 24, size + 24), CREAM_50 + (255,))
        card.paste(ph, (12, 12))
        card = card.rotate(-2.2 * a0, resample=Image.BICUBIC, expand=True)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay.alpha_composite(card, ((W - card.width) // 2, 230 - int(20 * (1 - a0))))
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a0)))
        f.alpha_composite(lay)
        d = ImageDraw.Draw(f)

        def line(txt, fnt, y, fill, delay):
            a = ease((p - delay) / 0.5)
            if a > 0:
                w = d.textlength(txt, font=fnt)
                d.text(((W - w) / 2, y + 18 * (1 - a)), txt, font=fnt, fill=fill + (int(255 * a),))

        tf, tl = fit_lines(d, self.p["title"], "Playfair-600.ttf", 84, W - 160, 2, 56)
        y = 920
        for k, tx in enumerate(tl):
            line(tx, tf, y, TITLE_GREEN, 0.45 + 0.1 * k)
            y += int(tf.size * 1.2)
        line(f"{price_line(self.p)}  ·  {shipping_line(self.p)}", font("Karla-700.ttf", 40), y + 50, GOLD_600, 0.8)
        line("thebookswanderer.com", font("Karla-400.ttf", 40), y + 120, INK, 0.95)
        return f.convert("RGB")

    def frame(self, t):
        if t >= END_START:
            fr = self.end(t)
            if t < END_START + XFADE:
                fr = Image.blend(self.scene(3, t), fr, ease((t - END_START) / XFADE))
            return fr
        idx = min(3, int(t // SCENE))
        fr = self.scene(idx, t)
        if idx > 0 and t < idx * SCENE + XFADE:
            fr = Image.blend(self.scene(idx - 1, t), fr, ease((t - idx * SCENE) / XFADE))
        if t < 0.35:
            fr = Image.blend(self.bg_dark, fr, ease(t / 0.35))
        return fr


def render(p: dict, images: list[Image.Image], out: Path, seed: int) -> None:
    music = sorted((SOCIAL / "music").glob("*.m4a"))
    track = music[seed % len(music)]
    reel = Reel(p, images, seed)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(track),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(out)],
        stdin=subprocess.PIPE,
    )
    for i in range(int(DUR * FPS)):
        ff.stdin.write(reel.frame(i / FPS).tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg failed")


# ── publishing ────────────────────────────────────────────────────────────

class Meta:
    def __init__(self):
        self.page = (os.getenv("FB_PAGE_ID") or "").strip()
        self.token = (os.getenv("FB_PAGE_TOKEN") or "").strip()
        if not (self.page and self.token):
            raise SystemExit("FB_PAGE_ID / FB_PAGE_TOKEN missing")
        self.c = httpx.Client(timeout=120)

    def _ok(self, r):
        try:
            j = r.json()
        except ValueError:
            j = {"raw": r.text[:300]}
        if r.status_code >= 400 or "error" in j:
            raise RuntimeError(f"HTTP {r.status_code}: {str(j).replace(self.token, '***')[:400]}")
        return j

    def _upload(self, url, video: Path):
        headers = {"Authorization": f"OAuth {self.token}", "offset": "0",
                   "file_size": str(video.stat().st_size), "Content-Type": "application/octet-stream"}
        return self._ok(self.c.post(url, headers=headers, content=video.read_bytes(), timeout=300))

    def facebook(self, video: Path, text: str) -> str:
        start = self._ok(self.c.post(f"{GRAPH}/{self.page}/video_reels",
                                     data={"upload_phase": "start", "access_token": self.token}))
        vid = start["video_id"]
        self._upload(f"{RUPLOAD}/video-upload/v21.0/{vid}", video)
        self._ok(self.c.post(f"{GRAPH}/{self.page}/video_reels", data={
            "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
            "description": text, "access_token": self.token}))
        return vid

    def instagram(self, video: Path, text: str) -> str:
        ig = self._ok(self.c.get(f"{GRAPH}/{self.page}", params={
            "fields": "instagram_business_account", "access_token": self.token}))
        ig_id = ig["instagram_business_account"]["id"]
        cont = self._ok(self.c.post(f"{GRAPH}/{ig_id}/media", data={
            "media_type": "REELS", "upload_type": "resumable", "caption": text,
            "share_to_feed": "true", "thumb_offset": "14500", "access_token": self.token}))
        self._upload(f"{RUPLOAD}/ig-api-upload/v21.0/{cont['id']}", video)
        for _ in range(60):
            st = self._ok(self.c.get(f"{GRAPH}/{cont['id']}", params={
                "fields": "status_code", "access_token": self.token}))
            if st.get("status_code") == "FINISHED":
                break
            if st.get("status_code") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram processing failed: {st}")
            time.sleep(5)
        else:
            raise RuntimeError("Instagram container never finished")
        pub = self._ok(self.c.post(f"{GRAPH}/{ig_id}/media_publish", data={
            "creation_id": cont["id"], "access_token": self.token}))
        return pub["id"]


# ── Pinterest ─────────────────────────────────────────────────────────────

PINTEREST_EXTRA_IMAGE_PINS = int(os.getenv("SOCIAL_PINTEREST_IMAGE_PINS", "2"))


def pinterest_round(slug: str, video: Path) -> dict:
    """The day's reel as a video pin, plus a couple of image pins that rotate
    through the product's other photos and designs. Never fails the run."""
    import asyncio

    from services import pinterest as pin
    from services import pinterest_jobs as jobs

    if not pin.is_configured() or not jobs.auto_pin_enabled():
        return {"skipped": "pinterest not configured or auto pins disabled"}
    from database import SessionLocal, init_db
    from models import Product

    init_db()
    db = SessionLocal()
    out: dict = {}
    try:
        prod = db.query(Product).filter(Product.slug == slug, Product.active.is_(True)).first()
        if not prod:
            return {"skipped": "product not in DB"}
        board = jobs.board_id_for_category(prod.category)
        payload = pin.product_pin_payload(prod.to_detail())
        try:
            r = asyncio.run(pin.create_video_pin(
                board_id=board, title=payload["title"], description=payload["description"],
                link=payload["link"].replace("utm_campaign=pin", "utm_campaign=video_pin"),
                video_path=video, cover_image_url=payload["image_url"], alt_text=payload["alt_text"],
            ))
            out["video"] = str(r.get("id") or "")
            jobs._record(db, product=prod, board_id=board, pin_id=out["video"], kind="video")
        except Exception as exc:  # noqa: BLE001
            out["video_error"] = str(exc)[:300]
            jobs._record(db, product=prod, board_id=board, pin_id="", kind="video",
                         status="failed", error=str(exc))
        images = []
        for _ in range(max(0, PINTEREST_EXTRA_IMAGE_PINS)):
            r = asyncio.run(jobs.create_product_pin(db, prod, kind="drip", board_id=board))
            images.append(r.get("pin_id") or r.get("error"))
        out["images"] = images
        return out
    finally:
        db.close()


# ── main ──────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="render and print captions, post nothing")
    ap.add_argument("--slug")
    ap.add_argument("--at-hour", type=int, help="only run when it is this hour in New York")
    ap.add_argument("--out", help="keep the rendered video here")
    ap.add_argument("--facebook-only", action="store_true",
                    help="retry Facebook for today's entry (same product and reel), leave Instagram/Pinterest alone")
    args = ap.parse_args()

    now_ny = datetime.now(NY)
    if args.at_hour is not None and now_ny.hour != args.at_hour:
        return
    if (os.getenv("SOCIAL_POST_ENABLED", "1") or "").strip() == "0" and not args.dry_run:
        print("SOCIAL_POST_ENABLED=0, skipping")
        return
    today = now_ny.date().isoformat()
    state = load_state()
    if not args.dry_run and not args.slug and any(e["date"] == today and e.get("ok") for e in state):
        print(f"{today}: already posted, nothing to do")
        return

    retry = None
    if args.facebook_only:
        retry = next((e for e in reversed(state) if e["date"] == today), None)
        if not retry or retry.get("facebook"):
            print(f"{today}: nothing to retry on Facebook")
            return
        args.slug = retry["slug"]

    client = httpx.Client(timeout=40, headers={"User-Agent": "TheBooksWanderer social bot"})
    p = pick_product(client, state, args.slug)
    images = product_images(client, p)
    fb_text, ig_text = captions(p)
    seed = int(now_ny.strftime("%Y%m%d")) + p["id"]
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(args.out) if args.out else Path(tmp) / "reel.mp4"
        render(p, images, video, seed)
        print(f"{today} {p['slug']}: rendered {video.stat().st_size // 1024} KB")
        if args.dry_run:
            print("── Facebook ──\n" + fb_text + "\n── Instagram ──\n" + ig_text)
            return
        meta = Meta()
        if retry is not None:
            try:
                retry["facebook"] = meta.facebook(video, fb_text)
                retry.pop("facebook_error", None)
                print(f"  facebook: posted {retry['facebook']}")
            except Exception as exc:  # noqa: BLE001
                retry["facebook_error"] = str(exc)[:300]
                print(f"  facebook: FAILED {exc}")
            retry["ok"] = bool(retry.get("facebook") and retry.get("instagram"))
            save_state(state)
            if not retry["ok"]:
                raise SystemExit(1)
            return
        entry = {"date": today, "slug": p["slug"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        for name, fn, text in (("facebook", meta.facebook, fb_text), ("instagram", meta.instagram, ig_text)):
            try:
                entry[name] = fn(video, text)
                print(f"  {name}: posted {entry[name]}")
            except Exception as exc:  # noqa: BLE001
                entry[f"{name}_error"] = str(exc)[:300]
                print(f"  {name}: FAILED {exc}")
        try:
            entry["pinterest"] = pinterest_round(p["slug"], video)
            print(f"  pinterest: {entry['pinterest']}")
        except Exception as exc:  # noqa: BLE001
            entry["pinterest"] = {"error": str(exc)[:300]}
            print(f"  pinterest: FAILED {exc}")
        entry["ok"] = bool(entry.get("facebook") and entry.get("instagram"))
        state.append(entry)
        save_state(state)
        if not entry["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
