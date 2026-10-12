"""Self-hosted live analytics dashboard (/admin/live) — ported from mathrelaxing.store."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import case, func, inspect, text
from sqlalchemy.orm import Session

from database import SessionLocal, engine, get_db
from models import LiveEvent
from services import geo
from services import health as health_service

log = logging.getLogger("tbw.live")


def _ensure_schema():
    """Add columns introduced after the initial table creation. SQLite supports ADD COLUMN."""
    insp = inspect(engine)
    with engine.begin() as conn:
        if "live_events" in insp.get_table_names():
            existing = {c["name"] for c in insp.get_columns("live_events")}
            for col, sql in [
                ("source", "ALTER TABLE live_events ADD COLUMN source VARCHAR(60)"),
                ("medium", "ALTER TABLE live_events ADD COLUMN medium VARCHAR(40)"),
                ("campaign", "ALTER TABLE live_events ADD COLUMN campaign VARCHAR(120)"),
            ]:
                if col not in existing:
                    conn.execute(text(sql))


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

ADMIN_COOKIE = "tbw_live_admin"
ADMIN_MAX_AGE = 7 * 24 * 3600
IGNORE_COOKIE = "tbw_notrack"  # owner self-exclusion flag
IGNORE_MAX_AGE = 3 * 365 * 24 * 3600  # 3 years
ACTIVE_VISITOR_WINDOW = 5 * 60
ACTIVE_FUNNEL_WINDOW = 30 * 60
# Historical retention. Default = 365 days. Set LIVE_EVENT_RETENTION_DAYS=0 to keep forever.
EVENT_RETENTION_DAYS = int(os.getenv("LIVE_EVENT_RETENTION_DAYS", "365"))
SITE_HOST = "thebookswanderer.com"

VALID_EVENTS = {
    "pageview",
    "product_view",
    "add_to_cart",
    "cart_view",
    "checkout_start",
    "payment_redirect",
    "purchase",
}


def _admin_password() -> str:
    return (os.getenv("LIVE_ADMIN_PASSWORD") or "").strip()


def _admin_user() -> str:
    return (os.getenv("LIVE_ADMIN_USER") or "tbw").strip()

def _cookie_sig(ts: int, username: str) -> str:
    key = (_admin_password() + str(ts) + username).encode()
    return hmac.new(key, digestmod=hashlib.sha256).hexdigest()[:32]


def _make_cookie(username: str) -> str:
    ts = int(time.time())
    return f"{ts}.{username}.{_cookie_sig(ts, username)}"


def _valid_cookie(value: Optional[str]) -> bool:
    if not value:
        return False
    parts = value.split(".")
    if len(parts) != 3:
        return False
    ts_str, username, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    if time.time() - ts > ADMIN_MAX_AGE:
        return False
    return secrets.compare_digest(sig, _cookie_sig(ts, username))


def _valid_login(username: str, password: str) -> bool:
    expected = _admin_password()
    if not expected:
        return False
    return (secrets.compare_digest(username, _admin_user())
            and secrets.compare_digest(password, expected))


def _is_admin(request: Request) -> bool:
    return _valid_cookie(request.cookies.get(ADMIN_COOKIE))


def _ignore_token() -> str:
    """Signed value for the owner self-exclusion cookie."""
    return hmac.new(_admin_password().encode(), b"live-ignore", hashlib.sha256).hexdigest()[:32]


def _ignored_ips() -> set:
    """Owner IPs to exclude server-side (comma-separated in LIVE_IGNORE_IPS).
    Useful for excluding the owner's own machine without relying on a per-browser
    cookie. Note: home IPs can be dynamic — pair with the cookie method for a
    durable exclusion."""
    raw = os.getenv("LIVE_IGNORE_IPS", "")
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def _is_ignored(request: Request) -> bool:
    if request.cookies.get(IGNORE_COOKIE) == _ignore_token():
        return True
    ips = _ignored_ips()
    if ips and (geo.extract_client_ip(request) or "") in ips:
        return True
    return False


def _login_redirect() -> RedirectResponse:
    return RedirectResponse("/admin/live/login", status_code=303)


def _classify_ua(ua: str) -> str:
    ua_l = (ua or "").lower()
    bot_sigs = ("bot", "crawler", "spider", "headless", "lighthouse", "pagespeed",
                "googlebot", "bingbot", "slurp", "duckduckbot", "baiduspider",
                "yandex", "sogou", "facebookexternalhit", "meta-externalads",
                "libredtail", "silver.inc", "censysinspect", "infrawatch",
                "go-http-client", "python-requests", "curl/", "wget")
    if any(s in ua_l for s in bot_sigs):
        return "bot"
    if "mobile" in ua_l or "iphone" in ua_l or "android" in ua_l:
        return "mobile"
    return "desktop"


_SOCIAL_HOSTS = ("facebook.", "fb.", "instagram.", "threads.")


def _meta_bot(ip: str, geo_info: dict, payload: "TrackPayload") -> Optional[str]:
    """Meta's link checkers render pages in a normal browser, so the UA filter
    misses them: a reel's link drew five "visitors" within 20 s of posting,
    all from Meta (Prineville, Forest City) or cloud (Boardman) hosts.

    Anything on Meta's own network is dropped. Cloud-hosted traffic is only
    dropped when it arrives from Facebook/Instagram: people tap those links on
    home or mobile connections, not from a data centre.
    """
    asn = (geo_info.get("asn") or "").upper()
    if asn.startswith("AS32934 ") or geo.is_meta_ip(ip):
        return "meta"
    if not geo_info.get("hosting"):
        return None
    ref = (payload.referrer or "").lower()
    path = (payload.path or "").lower()
    src = (payload.source or "").lower()
    social = (
        "fbclid=" in path
        or src in ("facebook", "instagram", "fb", "ig", "threads")
        or any(h in ref for h in _SOCIAL_HOSTS)
    )
    return "meta-cloud" if social else None


def _hash_ip(ip: str) -> str:
    return hashlib.sha256((ip + _admin_password()).encode()).hexdigest()[:16]


# ── Ingesta pública ────────────────────────────────────────────────────────

class TrackPayload(BaseModel):
    type: str
    session_id: str = Field(min_length=8, max_length=64)
    path: Optional[str] = None
    referrer: Optional[str] = None
    product_slug: Optional[str] = None
    value: Optional[float] = None
    source: Optional[str] = None
    medium: Optional[str] = None
    campaign: Optional[str] = None
    extra: Optional[dict] = None


@router.post("/api/track")
async def track(request: Request, db: Session = Depends(get_db)):
    # Owner self-exclusion: skip recording entirely for browsers flagged as
    # internal (via /admin/live/ignore-me). Keeps the owner's own testing out
    # of the stats. Cookie is sent with same-origin fetch/sendBeacon.
    if _is_ignored(request):
        return {"ok": True, "ignored": True}

    # Read the raw body and parse JSON ourselves instead of relying on FastAPI's
    # automatic body validation. `navigator.sendBeacon` (used for pageviews,
    # which fire during page unload) frequently sends the body as text/plain or
    # with no Content-Type at all — especially on Safari and mobile browsers.
    # FastAPI's typed body param rejects those with 422, silently dropping ~44%
    # of real visits. Parsing the raw bytes makes ingestion content-type-agnostic.
    try:
        raw = await request.body()
        data = json.loads(raw) if raw else None
    except Exception:
        return JSONResponse({"ok": False, "error": "bad json"}, status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"ok": False, "error": "bad payload"}, status_code=400)
    try:
        payload = TrackPayload(**data)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": "validation", "detail": str(exc)[:200]}, status_code=400)

    if payload.type not in VALID_EVENTS:
        return JSONResponse({"ok": False, "error": "unknown event"}, status_code=400)

    ua = request.headers.get("user-agent", "")
    ua_class = _classify_ua(ua)
    ip = geo.extract_client_ip(request) or ""

    if ua_class == "bot":
        return {"ok": True, "dropped": "bot"}

    geo_info = geo.lookup(ip)
    meta_bot = _meta_bot(ip, geo_info, payload)
    if meta_bot:
        return {"ok": True, "dropped": meta_bot}

    ref_domain = None
    if payload.referrer:
        try:
            from urllib.parse import urlparse
            host = urlparse(payload.referrer).hostname or ""
            if host and not host.endswith(SITE_HOST):
                ref_domain = host
        except Exception:
            ref_domain = None

    ev = LiveEvent(
        ts=datetime.utcnow(),
        session_id=payload.session_id[:64],
        event_type=payload.type,
        path=(payload.path or "")[:500] or None,
        referrer_domain=ref_domain,
        country=geo_info.get("country"),
        country_name=geo_info.get("country_name"),
        city=geo_info.get("city"),
        ua_class=ua_class,
        product_slug=(payload.product_slug or "")[:120] or None,
        value_usd=payload.value if payload.value is not None else None,
        ip_hash=_hash_ip(ip) if ip else None,
        source=(payload.source or "")[:60].lower() or None,
        medium=(payload.medium or "")[:40].lower() or None,
        campaign=(payload.campaign or "")[:120] or None,
        payload=json.dumps(payload.extra)[:2000] if payload.extra else None,
    )
    db.add(ev)
    db.commit()

    if payload.type in _ALERT_EVENTS:
        _queue_alert(payload, ev)

    return {"ok": True}


# ── Email alerts for cart / checkout ──────────────────────────────────────

_ALERT_EVENTS = ("add_to_cart", "checkout_start")
_ALERT_WINDOW_S = 30 * 60
_alert_sent: dict[tuple[str, str], float] = {}
_alert_tasks: set = set()


def _queue_alert(payload: "TrackPayload", ev: LiveEvent) -> None:
    """One email per session and event type every 30 minutes, sent in the
    background so the tracking call never waits on SMTP."""
    from services import email as email_service

    if os.getenv("SHOP_ALERTS_ENABLED", "1").strip() == "0" or not email_service.configured():
        return
    now = time.time()
    key = (payload.session_id, payload.type)
    if now - _alert_sent.get(key, 0) < _ALERT_WINDOW_S:
        return
    _alert_sent[key] = now
    if len(_alert_sent) > 5000:
        for k, t in list(_alert_sent.items()):
            if now - t > _ALERT_WINDOW_S:
                _alert_sent.pop(k, None)

    place = ", ".join(p for p in (ev.city, ev.country_name) if p)
    source = " / ".join(p for p in (ev.source or ev.referrer_domain, ev.campaign) if p)
    extra = payload.extra or {}
    detail = ", ".join(f"{k}={extra[k]}" for k in ("quantity", "lines") if k in extra)
    task = asyncio.create_task(email_service.send_shop_alert(
        payload.type,
        product=ev.product_slug or "",
        value=ev.value_usd,
        place=place,
        source=source or "direct",
        path=ev.path or "",
        detail=detail,
    ))
    _alert_tasks.add(task)
    task.add_done_callback(_alert_tasks.discard)


# ── Snapshot & SSE ────────────────────────────────────────────────────────

def _flag(cc: Optional[str]) -> str:
    if not cc or len(cc) != 2:
        return "🌐"
    return chr(0x1F1E6 + ord(cc[0].upper()) - ord("A")) + chr(0x1F1E6 + ord(cc[1].upper()) - ord("A"))


def _norm_path():
    """SQL expression: path without its query string, so '/' and
    '/?ttclid=...&utm_...' collapse into a single '/' row in Top Pages."""
    return case(
        (func.instr(LiveEvent.path, "?") > 0,
         func.substr(LiveEvent.path, 1, func.instr(LiveEvent.path, "?") - 1)),
        else_=LiveEvent.path,
    )


# Maps utm_source values and referrer hostnames → (group_name, emoji)
SOURCE_GROUPS = {
    "facebook": ("Facebook", "📘"), "fb": ("Facebook", "📘"), "meta": ("Facebook", "📘"),
    "facebook.com": ("Facebook", "📘"), "m.facebook.com": ("Facebook", "📘"),
    "l.facebook.com": ("Facebook", "📘"), "lm.facebook.com": ("Facebook", "📘"),
    "www.facebook.com": ("Facebook", "📘"),
    "instagram": ("Instagram", "📷"), "ig": ("Instagram", "📷"),
    "instagram.com": ("Instagram", "📷"), "l.instagram.com": ("Instagram", "📷"),
    "www.instagram.com": ("Instagram", "📷"),
    "google": ("Google", "🔍"), "google.com": ("Google", "🔍"),
    "www.google.com": ("Google", "🔍"), "google-ads": ("Google Ads", "💰"),
    "bing": ("Bing", "🔍"), "bing.com": ("Bing", "🔍"), "www.bing.com": ("Bing", "🔍"),
    "duckduckgo.com": ("DuckDuckGo", "🦆"),
    "tiktok": ("TikTok", "🎵"), "tiktok.com": ("TikTok", "🎵"),
    "www.tiktok.com": ("TikTok", "🎵"),
    "pinterest": ("Pinterest", "📌"), "pinterest.com": ("Pinterest", "📌"),
    "www.pinterest.com": ("Pinterest", "📌"), "pin": ("Pinterest", "📌"),
    "twitter": ("Twitter/X", "🐦"), "twitter.com": ("Twitter/X", "🐦"),
    "t.co": ("Twitter/X", "🐦"), "x.com": ("Twitter/X", "🐦"),
    "youtube": ("YouTube", "▶️"), "youtube.com": ("YouTube", "▶️"),
    "www.youtube.com": ("YouTube", "▶️"), "m.youtube.com": ("YouTube", "▶️"),
    "reddit": ("Reddit", "🤖"), "reddit.com": ("Reddit", "🤖"),
    "www.reddit.com": ("Reddit", "🤖"), "old.reddit.com": ("Reddit", "🤖"),
    "linkedin.com": ("LinkedIn", "💼"), "www.linkedin.com": ("LinkedIn", "💼"),
    "ebay": ("eBay", "🛒"), "ebay.com": ("eBay", "🛒"),
    "gumroad.com": ("Gumroad", "🛍"),
    "yahoo.com": ("Yahoo", "🔍"),
}


def _normalize_source(source: Optional[str], referrer_domain: Optional[str], medium: Optional[str] = None) -> tuple:
    """Returns (group_name, emoji). Falls back to raw values if unknown."""
    candidates = []
    if source:
        candidates.append(source.lower().strip())
    if referrer_domain:
        candidates.append(referrer_domain.lower().strip())
    for c in candidates:
        if c in SOURCE_GROUPS:
            return SOURCE_GROUPS[c]
        for key, val in SOURCE_GROUPS.items():
            if "." in key and (c == key or c.endswith("." + key)):
                return val
    if not candidates:
        return ("Direct", "↪️")
    return (candidates[0], "🌐")


def _build_snapshot(db: Session) -> dict:
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    visitor_cutoff = now - timedelta(seconds=ACTIVE_VISITOR_WINDOW)
    funnel_cutoff = now - timedelta(seconds=ACTIVE_FUNNEL_WINDOW)

    # Active visitors: distinct sessions with any event in last 5 min,
    # excluding server-side synthetic events (purchases recorded by webhooks).
    active_visitors = db.query(func.count(func.distinct(LiveEvent.session_id))) \
        .filter(LiveEvent.ts >= visitor_cutoff,
                func.coalesce(LiveEvent.ua_class, "") != "server").scalar() or 0

    # Last event per session in funnel window — used for cart/checkout state
    sub = db.query(
        LiveEvent.session_id,
        func.max(LiveEvent.ts).label("last_ts"),
    ).filter(LiveEvent.ts >= funnel_cutoff).group_by(LiveEvent.session_id).subquery()

    funnel_rows = db.query(LiveEvent).join(
        sub, (LiveEvent.session_id == sub.c.session_id) & (LiveEvent.ts == sub.c.last_ts)
    ).all()

    active_carts = 0
    active_checkouts = 0
    carts_value = 0.0
    checkouts_value = 0.0
    cart_sessions = []
    checkout_sessions = []
    for ev in funnel_rows:
        if ev.event_type == "purchase":
            continue
        if ev.event_type in ("add_to_cart", "cart_view"):
            active_carts += 1
            if ev.value_usd:
                carts_value += ev.value_usd
            cart_sessions.append(ev)
        elif ev.event_type in ("checkout_start", "payment_redirect"):
            active_checkouts += 1
            if ev.value_usd:
                checkouts_value += ev.value_usd
            checkout_sessions.append(ev)

    # Today aggregates
    today_pageviews = db.query(func.count(LiveEvent.id)) \
        .filter(LiveEvent.ts >= today_start, LiveEvent.event_type == "pageview").scalar() or 0
    today_sessions = db.query(func.count(func.distinct(LiveEvent.session_id))) \
        .filter(LiveEvent.ts >= today_start,
                func.coalesce(LiveEvent.ua_class, "") != "server").scalar() or 0
    today_purchases = db.query(func.count(LiveEvent.id)) \
        .filter(LiveEvent.ts >= today_start, LiveEvent.event_type == "purchase").scalar() or 0
    today_revenue = db.query(func.coalesce(func.sum(LiveEvent.value_usd), 0)) \
        .filter(LiveEvent.ts >= today_start, LiveEvent.event_type == "purchase").scalar() or 0

    # Top pages today (pageviews) — query string stripped so the homepage
    # doesn't fragment across dozens of ?ttclid=/?utm= variants.
    _np = _norm_path()
    top_pages = db.query(_np.label("p"), func.count(LiveEvent.id).label("c")) \
        .filter(LiveEvent.ts >= today_start, LiveEvent.event_type == "pageview", LiveEvent.path.isnot(None)) \
        .group_by(_np).order_by(func.count(LiveEvent.id).desc()).limit(6).all()

    # Top sources today — grouped (Facebook, Instagram, Google, …) using
    # utm_source first, falling back to referrer hostname, both normalized.
    src_rows = db.query(
        LiveEvent.session_id, LiveEvent.source, LiveEvent.referrer_domain, LiveEvent.medium,
    ).filter(LiveEvent.ts >= today_start).all()
    source_groups: dict[str, list] = {}
    paid_sessions: set = set()
    for sid_v, src_v, ref_v, med_v in src_rows:
        grp, emo = _normalize_source(src_v, ref_v, med_v)
        bucket = source_groups.setdefault(grp, [emo, set(), 0])
        bucket[1].add(sid_v)
        if med_v and any(p in med_v for p in ("paid", "cpc", "ppc", "ads")):
            paid_sessions.add(sid_v)
    top_sources_pretty = sorted(
        [(g, e, len(s)) for g, (e, s, _) in source_groups.items()],
        key=lambda x: -x[2],
    )[:6]

    # Top campaigns today (only when utm_campaign was present)
    top_campaigns = db.query(
        LiveEvent.campaign,
        func.count(func.distinct(LiveEvent.session_id)).label("c"),
    ).filter(LiveEvent.ts >= today_start, LiveEvent.campaign.isnot(None)) \
     .group_by(LiveEvent.campaign) \
     .order_by(func.count(func.distinct(LiveEvent.session_id)).desc()).limit(6).all()

    # Top countries today
    top_countries = db.query(
        LiveEvent.country, LiveEvent.country_name,
        func.count(func.distinct(LiveEvent.session_id)).label("c"),
    ).filter(LiveEvent.ts >= today_start, LiveEvent.country.isnot(None)) \
     .group_by(LiveEvent.country, LiveEvent.country_name) \
     .order_by(func.count(func.distinct(LiveEvent.session_id)).desc()).limit(6).all()

    # Recent events feed (last 25)
    recent = db.query(LiveEvent).order_by(LiveEvent.ts.desc()).limit(25).all()

    def _fmt_ev(e: LiveEvent) -> dict:
        grp, emo = _normalize_source(e.source, e.referrer_domain, e.medium)
        return {
            "ts": e.ts.isoformat() + "Z",
            "ago_s": int((now - e.ts).total_seconds()),
            "type": e.event_type,
            "path": e.path,
            "product": e.product_slug,
            "value": e.value_usd,
            "country": e.country,
            "country_name": e.country_name,
            "flag": _flag(e.country),
            "city": e.city,
            "src": grp,
            "src_emoji": emo,
            "campaign": e.campaign,
            "medium": e.medium,
            "is_paid": bool(e.medium and any(p in e.medium for p in ("paid", "cpc", "ppc", "ads"))),
            "ua_class": e.ua_class,
            "session": e.session_id[:8],
        }

    return {
        "now": now.isoformat() + "Z",
        "active_visitors": active_visitors,
        "active_carts": active_carts,
        "active_checkouts": active_checkouts,
        "carts_value": round(carts_value, 2),
        "checkouts_value": round(checkouts_value, 2),
        "today": {
            "pageviews": today_pageviews,
            "sessions": today_sessions,
            "purchases": today_purchases,
            "revenue": round(float(today_revenue), 2),
        },
        "top_pages": [{"path": p, "count": c} for p, c in top_pages],
        "top_sources": [{"src": g, "emoji": e, "count": c} for g, e, c in top_sources_pretty],
        "top_campaigns": [{"name": n, "count": c} for n, c in top_campaigns],
        "paid_sessions_today": len(paid_sessions),
        "top_countries": [
            {"code": cc, "name": cn or cc, "flag": _flag(cc), "count": c}
            for cc, cn, c in top_countries
        ],
        "active_cart_sessions": [_fmt_ev(e) for e in cart_sessions[:10]],
        "active_checkout_sessions": [_fmt_ev(e) for e in checkout_sessions[:10]],
        "recent_events": [_fmt_ev(e) for e in recent],
    }


@router.get("/admin/live/snapshot")
async def snapshot(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        raise HTTPException(status_code=401, detail="auth required")
    return _build_snapshot(db)


@router.get("/admin/live/health")
async def live_health(request: Request):
    """Chequeos internos + ultimo latido externo. Ver services/health.py."""
    if not _is_admin(request):
        raise HTTPException(status_code=401, detail="auth required")
    return health_service.snapshot()


@router.get("/admin/live/stream")
async def stream(request: Request):
    if not _is_admin(request):
        raise HTTPException(status_code=401, detail="auth required")

    async def gen():
        last_cleanup = time.time()
        while True:
            if await request.is_disconnected():
                break
            db = SessionLocal()
            try:
                snap = _build_snapshot(db)
                now_t = time.time()
                if EVENT_RETENTION_DAYS > 0 and now_t - last_cleanup > 3600:
                    cutoff = datetime.utcnow() - timedelta(days=EVENT_RETENTION_DAYS)
                    db.query(LiveEvent).filter(LiveEvent.ts < cutoff).delete()
                    db.commit()
                    last_cleanup = now_t
            finally:
                db.close()
            yield f"data: {json.dumps(snap)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


# ── Admin pages ───────────────────────────────────────────────────────────

@router.get("/admin/live", response_class=HTMLResponse)
async def live_dashboard(request: Request):
    if not _is_admin(request):
        return _login_redirect()
    return templates.TemplateResponse("admin_live.html", {"request": request})


@router.get("/admin/live/login", response_class=HTMLResponse)
async def live_login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse("admin_live_login.html", {
        "request": request,
        "error": error,
    })


@router.post("/admin/live/login")
async def live_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if not _valid_login(username, password):
        return RedirectResponse("/admin/live/login?error=1", status_code=303)
    resp = RedirectResponse("/admin/live", status_code=303)
    resp.set_cookie(
        ADMIN_COOKIE, _make_cookie(username),
        max_age=ADMIN_MAX_AGE, httponly=True, secure=True, samesite="lax", path="/",
    )
    return resp


@router.get("/admin/live/logout")
async def live_logout():
    resp = RedirectResponse("/admin/live/login", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE, path="/")
    return resp


_IGNORE_PAGE = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{background:linear-gradient(180deg,#f8f2e5 0%,#efe6d0 100%);color:#24291f;
font-family:Georgia,serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;text-align:center;padding:20px;}}
.card{{background:#fffdf8;border:1px solid #e0d4b8;border-radius:16px;padding:32px 36px;max-width:420px;
box-shadow:0 10px 28px rgba(27,55,40,.08);}}
h1{{font-size:20px;margin:0 0 10px;color:{color};font-weight:600;}}
p{{color:#5c6157;font-size:14px;line-height:1.55;margin:0 0 16px;font-family:system-ui,sans-serif;}}
a{{color:#2b5240;font-size:13px;font-weight:600;text-decoration:none;font-family:system-ui,sans-serif;}}
</style></head><body><div class="card">
<h1>{heading}</h1><p>{body}</p><a href="/admin/live">← Back to Live</a></div></body></html>"""


@router.get("/admin/live/ignore-me", response_class=HTMLResponse)
async def live_ignore_me(request: Request):
    """Flag THIS browser as internal so the owner's own visits are not tracked."""
    if not _is_admin(request):
        return _login_redirect()
    resp = HTMLResponse(_IGNORE_PAGE.format(
        title="Tráfico excluido",
        color="#5fbf7a",
        heading="✓ Tu navegador queda excluido",
        body="A partir de ahora tus visitas desde este navegador NO se registran en el dashboard. "
             "Dura ~3 años o hasta que borres cookies. Para reactivar el registro, entra a "
             "/admin/live/track-me.",
    ))
    resp.set_cookie(IGNORE_COOKIE, _ignore_token(), max_age=IGNORE_MAX_AGE,
                    httponly=True, secure=True, samesite="lax", path="/")
    return resp


@router.get("/admin/live/track-me", response_class=HTMLResponse)
async def live_track_me(request: Request):
    """Undo self-exclusion: start tracking this browser again."""
    if not _is_admin(request):
        return _login_redirect()
    resp = HTMLResponse(_IGNORE_PAGE.format(
        title="Tráfico reactivado",
        color="#c8a96e",
        heading="✓ Registro reactivado",
        body="Tus visitas desde este navegador vuelven a registrarse normalmente en el dashboard.",
    ))
    resp.delete_cookie(IGNORE_COOKIE, path="/")
    return resp


# ── Historical analytics ──────────────────────────────────────────────────

def _history_payload(db: Session, days: int) -> dict:
    """Build history payload for the last `days` calendar days (UTC), including today.

    Previously the daily chart used a rolling window of `days*24h` but only
    emitted `days` date buckets starting at start.date(), which dropped *today*
    whenever `now` was past midnight. Totals and daily series are now aligned
    on UTC calendar days: [today-(days-1), today] inclusive.
    """
    now = datetime.utcnow()
    end = now
    end_date = now.date()
    start_date = end_date - timedelta(days=days - 1)
    # Midnight UTC of the first day in the range
    start = datetime(start_date.year, start_date.month, start_date.day)
    # Previous period: the `days` calendar days immediately before start
    prev_end = start
    prev_start = start - timedelta(days=days)

    def _totals(t0, t1):
        pv = db.query(func.count(LiveEvent.id)).filter(
            LiveEvent.event_type == "pageview", LiveEvent.ts >= t0, LiveEvent.ts < t1,
            func.coalesce(LiveEvent.ua_class, "") != "server",
        ).scalar() or 0
        ses = db.query(func.count(func.distinct(LiveEvent.session_id))).filter(
            LiveEvent.ts >= t0, LiveEvent.ts < t1,
            func.coalesce(LiveEvent.ua_class, "") != "server",
        ).scalar() or 0
        pur = db.query(func.count(LiveEvent.id)).filter(
            LiveEvent.event_type == "purchase", LiveEvent.ts >= t0, LiveEvent.ts < t1,
        ).scalar() or 0
        rev = db.query(func.coalesce(func.sum(LiveEvent.value_usd), 0)).filter(
            LiveEvent.event_type == "purchase", LiveEvent.ts >= t0, LiveEvent.ts < t1,
        ).scalar() or 0
        return {"pageviews": pv, "sessions": ses, "purchases": pur, "revenue": round(float(rev), 2)}

    current = _totals(start, end)
    previous = _totals(prev_start, prev_end)

    # Daily series (one row per UTC date in the range, including today)
    raw_daily = db.query(
        func.date(LiveEvent.ts).label("d"),
        func.sum(case((LiveEvent.event_type == "pageview", 1), else_=0)).label("pv"),
        func.count(func.distinct(LiveEvent.session_id)).label("ses"),
        func.sum(case((LiveEvent.event_type == "purchase", 1), else_=0)).label("pur"),
        func.sum(case((LiveEvent.event_type == "purchase", LiveEvent.value_usd), else_=0)).label("rev"),
    ).filter(LiveEvent.ts >= start, LiveEvent.ts < end,
             func.coalesce(LiveEvent.ua_class, "") != "server") \
     .group_by(func.date(LiveEvent.ts)).all()
    by_day = {str(r.d): r for r in raw_daily}

    # Purchase totals include server-side events (we excluded server above for sessions/pageviews
    # but want purchase counts intact). Recompute purchase/revenue by day separately.
    raw_purchase = db.query(
        func.date(LiveEvent.ts).label("d"),
        func.count(LiveEvent.id).label("pur"),
        func.coalesce(func.sum(LiveEvent.value_usd), 0).label("rev"),
    ).filter(LiveEvent.event_type == "purchase",
             LiveEvent.ts >= start, LiveEvent.ts < end) \
     .group_by(func.date(LiveEvent.ts)).all()
    purchase_by_day = {str(r.d): (r.pur, float(r.rev)) for r in raw_purchase}

    daily = []
    # Inclusive UTC calendar dates: start_date .. end_date (today)
    for i in range(days):
        d = start_date + timedelta(days=i)
        dstr = d.isoformat()
        row = by_day.get(dstr)
        pur, rev = purchase_by_day.get(dstr, (0, 0.0))
        daily.append({
            "date": dstr,
            "pageviews": int(row.pv) if row else 0,
            "sessions": int(row.ses) if row else 0,
            "purchases": int(pur),
            "revenue": round(rev, 2),
        })

    # Hourly today (last 24h, UTC hour buckets)
    last24 = now - timedelta(hours=24)
    raw_hourly = db.query(
        func.strftime("%H", LiveEvent.ts).label("h"),
        func.count(LiveEvent.id).label("pv"),
        func.count(func.distinct(LiveEvent.session_id)).label("ses"),
    ).filter(LiveEvent.event_type == "pageview", LiveEvent.ts >= last24,
             func.coalesce(LiveEvent.ua_class, "") != "server") \
     .group_by(func.strftime("%H", LiveEvent.ts)).all()
    hourly_map = {r.h: (int(r.pv), int(r.ses)) for r in raw_hourly}
    current_hour = now.hour
    hourly = []
    for i in range(24):
        h = (current_hour - 23 + i) % 24
        h_str = f"{h:02d}"
        pv, ses = hourly_map.get(h_str, (0, 0))
        hourly.append({"hour": h_str, "pageviews": pv, "sessions": ses})

    # Top tables over the whole range (query string stripped — see _norm_path)
    _np = _norm_path()
    top_pages = db.query(_np.label("p"), func.count(LiveEvent.id).label("c")) \
        .filter(LiveEvent.event_type == "pageview", LiveEvent.ts >= start, LiveEvent.ts < end,
                LiveEvent.path.isnot(None),
                func.coalesce(LiveEvent.ua_class, "") != "server") \
        .group_by(_np).order_by(func.count(LiveEvent.id).desc()).limit(10).all()

    src_rows = db.query(
        LiveEvent.session_id, LiveEvent.source, LiveEvent.referrer_domain, LiveEvent.medium,
    ).filter(LiveEvent.ts >= start, LiveEvent.ts < end,
             func.coalesce(LiveEvent.ua_class, "") != "server").all()
    src_groups: dict = {}
    for sid_v, src_v, ref_v, med_v in src_rows:
        grp, emo = _normalize_source(src_v, ref_v, med_v)
        bucket = src_groups.setdefault(grp, [emo, set()])
        bucket[1].add(sid_v)
    top_sources = sorted(
        [(g, e, len(s)) for g, (e, s) in src_groups.items()],
        key=lambda x: -x[2],
    )[:10]

    top_campaigns = db.query(
        LiveEvent.campaign, func.count(func.distinct(LiveEvent.session_id)).label("c"),
    ).filter(LiveEvent.ts >= start, LiveEvent.ts < end, LiveEvent.campaign.isnot(None)) \
     .group_by(LiveEvent.campaign) \
     .order_by(func.count(func.distinct(LiveEvent.session_id)).desc()).limit(10).all()

    top_countries = db.query(
        LiveEvent.country, LiveEvent.country_name,
        func.count(func.distinct(LiveEvent.session_id)).label("c"),
    ).filter(LiveEvent.ts >= start, LiveEvent.ts < end, LiveEvent.country.isnot(None),
             func.coalesce(LiveEvent.ua_class, "") != "server") \
     .group_by(LiveEvent.country, LiveEvent.country_name) \
     .order_by(func.count(func.distinct(LiveEvent.session_id)).desc()).limit(10).all()

    top_products = db.query(
        LiveEvent.product_slug,
        func.sum(case((LiveEvent.event_type == "product_view", 1), else_=0)).label("views"),
        func.sum(case((LiveEvent.event_type == "add_to_cart", 1), else_=0)).label("carts"),
        func.sum(case((LiveEvent.event_type == "purchase", 1), else_=0)).label("sales"),
        func.sum(case((LiveEvent.event_type == "purchase", LiveEvent.value_usd), else_=0)).label("rev"),
    ).filter(LiveEvent.ts >= start, LiveEvent.ts < end, LiveEvent.product_slug.isnot(None)) \
     .group_by(LiveEvent.product_slug) \
     .order_by(func.sum(case((LiveEvent.event_type == "purchase", LiveEvent.value_usd), else_=0)).desc(),
               func.sum(case((LiveEvent.event_type == "product_view", 1), else_=0)).desc()) \
     .limit(10).all()

    def _delta(cur, prev):
        if not prev:
            return {"pct": None, "dir": "—"}
        pct = round((cur - prev) * 100 / prev, 1)
        return {"pct": pct, "dir": "up" if pct > 0 else ("down" if pct < 0 else "flat")}

    return {
        "days": days,
        "start": start.isoformat() + "Z",
        "end": end.isoformat() + "Z",
        "current": current,
        "previous": previous,
        "delta": {
            "pageviews": _delta(current["pageviews"], previous["pageviews"]),
            "sessions": _delta(current["sessions"], previous["sessions"]),
            "purchases": _delta(current["purchases"], previous["purchases"]),
            "revenue": _delta(current["revenue"], previous["revenue"]),
        },
        "daily": daily,
        "hourly": hourly,
        "top_pages": [{"path": p, "count": c} for p, c in top_pages],
        "top_sources": [{"src": g, "emoji": e, "count": c} for g, e, c in top_sources],
        "top_campaigns": [{"name": n, "count": c} for n, c in top_campaigns],
        "top_countries": [{"code": cc, "name": cn or cc, "flag": _flag(cc), "count": c}
                          for cc, cn, c in top_countries],
        "top_products": [{"slug": s, "views": int(v or 0), "carts": int(ca or 0),
                          "sales": int(sa or 0), "revenue": round(float(r or 0), 2)}
                         for s, v, ca, sa, r in top_products],
    }


@router.get("/admin/live/history/data")
async def history_data(request: Request, days: int = 30, db: Session = Depends(get_db)):
    if not _is_admin(request):
        raise HTTPException(status_code=401, detail="auth required")
    days = max(1, min(days, 365))
    return _history_payload(db, days)


@router.get("/admin/live/history", response_class=HTMLResponse)
async def history_page(request: Request, days: int = 30):
    if not _is_admin(request):
        return _login_redirect()
    return templates.TemplateResponse("admin_live_history.html", {
        "request": request, "default_days": days,
    })


# ── Digital products: upload the files buyers download ───────────────────
# Files go to DIGITAL_DIR (outside the web root); only /api/download/<token>
# ever serves them. Same login as the live dashboard.

from fastapi import File, UploadFile  # noqa: E402


@router.get("/admin/digital/", response_class=HTMLResponse)
async def digital_admin(request: Request, msg: Optional[str] = None, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return _login_redirect()
    import html as _h

    from models import Product
    from services import digital

    rows = db.query(Product).filter(Product.supplier == digital.SUPPLIER).order_by(Product.id).all()
    files = sorted(p.name for p in digital.digital_dir().glob("*") if p.is_file()) if digital.digital_dir().is_dir() else []

    def status(name: str) -> str:
        if not name:
            return '<span style="color:#a33">no file</span>'
        ok = digital.file_path(name) is not None
        return f'{_h.escape(name)} {"✅" if ok else "<span style=color:#a33>❌ missing on disk</span>"}'

    def form(pid: int, vid: int = 0) -> str:
        return (
            f'<form method="post" action="/admin/digital/upload" enctype="multipart/form-data" style="display:inline">'
            f'<input type="hidden" name="product_id" value="{pid}"><input type="hidden" name="variant_id" value="{vid}">'
            f'<input type="file" name="file" accept=".pdf,.zip,.epub,.png,.jpg" required> '
            f'<button>Upload</button></form>'
        )

    items = []
    for p in rows:
        vs = "".join(
            f"<li>{_h.escape(v.name or 'Option')} — {status(v.digital_file)} {form(p.id, v.id)}</li>"
            for v in p.active_variants()
        )
        items.append(
            f"<li style='margin-bottom:1rem'><strong>{_h.escape(p.title)}</strong> "
            f"<code>{_h.escape(p.slug)}</code> {'(active)' if p.active else '(hidden)'}<br>"
            f"Product file: {status(p.digital_file)} {form(p.id)}"
            f"{'<ul>' + vs + '</ul>' if vs else ''}</li>"
        )
    body = "".join(items) or "<li>No digital products yet. Create them with scripts/digital_products.py.</li>"
    note = f"<p style='background:#eef6ee;padding:.6rem'>{_h.escape(msg)}</p>" if msg else ""
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="robots" content="noindex">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Digital files</title></head>
<body style="font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem">
<h1>Digital files</h1>{note}
<p>Files are stored in <code>{_h.escape(str(digital.digital_dir()))}</code>, outside the public site.
A variant file overrides the product file.</p>
<ul>{body}</ul>
<h2>On disk</h2><ul>{''.join(f'<li>{_h.escape(f)}</li>' for f in files) or '<li>(empty)</li>'}</ul>
<p><a href="/admin/live">← Live dashboard</a></p></body></html>""")


@router.post("/admin/digital/upload")
async def digital_upload(
    request: Request,
    product_id: int = Form(...),
    variant_id: int = Form(0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return _login_redirect()
    import re as _re

    from models import Product, ProductVariant
    from services import digital

    p = db.get(Product, product_id)
    if not p or p.supplier != digital.SUPPLIER:
        raise HTTPException(404, "Not a digital product")
    v = db.get(ProductVariant, variant_id) if variant_id else None
    if v and v.product_id != p.id:
        raise HTTPException(400, "Variant does not belong to product")
    ext = (Path(file.filename or "").suffix or ".pdf").lower()
    stem = p.slug + (f"-{_re.sub(r'[^a-z0-9]+', '-', (v.name or str(v.id)).lower()).strip('-')}" if v else "")
    name = digital.safe_name(f"{stem}{ext}")
    if not name:
        raise HTTPException(400, f"Unsupported file type {ext}")
    folder = digital.digital_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{name}.part"
    size = 0
    with tmp.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            out.write(chunk)
    tmp.replace(folder / name)
    if v:
        v.digital_file = name
    else:
        p.digital_file = name
    db.commit()
    return RedirectResponse(f"/admin/digital/?msg=Saved+{name}+({size // 1024}+KB)", status_code=303)
