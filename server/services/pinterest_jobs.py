"""Pinterest auto-pin: launch pins on new products + daily drip."""
from __future__ import annotations

import logging
import os
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import PinterestPin, Product
from services import categories as cat_service
from services import pinterest as pin

logger = logging.getLogger("pinterest_jobs")

# Boards created for TheBooksWanderer (override via env anytime).
_DEFAULT_BOARDS = {
    "book-accessories": "1098948815264074272",
    "decor": "1098948815264074273",
    "ereader-accessories": "1098948815264074274",
    "shop": "1098948815264074275",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def auto_pin_enabled() -> bool:
    return _env_bool("PINTEREST_AUTO_PIN_ENABLED", True)


def launch_pin_enabled() -> bool:
    return _env_bool("PINTEREST_LAUNCH_PIN_ENABLED", True)


def pins_per_day() -> int:
    try:
        return max(0, int(os.getenv("PINTEREST_PINS_PER_DAY", "1")))
    except ValueError:
        return 1


def repin_cooldown_days() -> int:
    try:
        return max(1, int(os.getenv("PINTEREST_REPIN_COOLDOWN_DAYS", "45")))
    except ValueError:
        return 45


def board_id_for_category(category: str | None) -> str:
    """Map product category → Pinterest board id."""
    slug = cat_service.normalize_category(category)
    env_key = {
        "book-accessories": "PINTEREST_BOARD_BOOK_ACCESSORIES",
        "decor": "PINTEREST_BOARD_DECOR",
        "ereader-accessories": "PINTEREST_BOARD_EREADER",
    }.get(slug, "")
    if env_key:
        override = (os.getenv(env_key) or "").strip()
        if override:
            return override
    if slug in _DEFAULT_BOARDS:
        return _DEFAULT_BOARDS[slug]
    shop = (os.getenv("PINTEREST_BOARD_SHOP") or "").strip() or _DEFAULT_BOARDS["shop"]
    return shop


def shop_board_id() -> str:
    return (os.getenv("PINTEREST_BOARD_SHOP") or "").strip() or _DEFAULT_BOARDS["shop"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _record(
    db: Session,
    *,
    product: Product,
    board_id: str,
    pin_id: str,
    kind: str,
    status: str = "active",
    error: str = "",
) -> PinterestPin:
    if pin_id and status == "active":
        existing = db.query(PinterestPin).filter_by(pin_id=pin_id, status="active").first()
        if existing:
            return existing
    row = PinterestPin(
        product_id=product.id or 0,
        product_slug=product.slug or "",
        board_id=board_id,
        pin_id=pin_id or "",
        kind=kind,
        status=status,
        error=(error or "")[:2000],
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent publisher may have recorded the same Pinterest ID.
        existing = db.query(PinterestPin).filter_by(pin_id=pin_id, status="active").first() if pin_id else None
        if existing:
            return existing
        raise
    db.refresh(row)
    return row


def last_successful_pin_at(db: Session, slug: str) -> datetime | None:
    row = (
        db.query(PinterestPin)
        .filter(
            PinterestPin.product_slug == slug,
            PinterestPin.status == "active",
            PinterestPin.pin_id != "",
        )
        .order_by(PinterestPin.created_at.desc())
        .first()
    )
    return row.created_at if row else None


def already_launch_pinned(db: Session, slug: str) -> bool:
    n = (
        db.query(PinterestPin)
        .filter(
            PinterestPin.product_slug == slug,
            PinterestPin.kind == "launch",
            PinterestPin.status == "active",
            PinterestPin.pin_id != "",
        )
        .count()
    )
    return n > 0


def _rotate_image(db: Session, product: Product, detail: dict[str, Any], payload: dict[str, Any]) -> None:
    """Give each drip pin of a product a different picture.

    Cycles through the hero, the lifestyle shots and each variant's image, by
    how many pins the product already has. A variant picture gets that
    variant's name in the title and ?variant=<id> on the link, so the product
    page opens on the design the pin showed.
    """
    base = pin.public_base()

    def absolute(u: str) -> str:
        return base + u if u.startswith("/") else u

    choices: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for u in [detail.get("image_url") or "", *(detail.get("lifestyle_images") or [])]:
        if u and u not in seen:
            seen.add(u)
            choices.append((u, None))
    for v in product.active_variants():
        if v.image_url and v.image_url not in seen:
            seen.add(v.image_url)
            choices.append((v.image_url, v))
    if len(choices) < 2:
        return
    done = (
        db.query(PinterestPin)
        .filter(PinterestPin.product_slug == product.slug, PinterestPin.status == "active")
        .count()
    )
    img, variant = choices[done % len(choices)]
    payload["image_url"] = absolute(img)
    if variant is not None and len(product.active_variants()) > 1:
        payload["title"] = f"{product.title} — {variant.name}"[:100]
        payload["alt_text"] = payload["title"]
        payload["link"] += f"&variant={variant.id}"


async def create_product_pin(
    db: Session,
    product: Product,
    *,
    kind: str,
    board_id: str | None = None,
) -> dict[str, Any]:
    """Create one pin for a product and record it. Raises on hard config errors."""
    if not pin.is_configured():
        return {"ok": False, "error": "pinterest_not_configured"}
    if not product.active:
        return {"ok": False, "error": "product_inactive"}

    detail = product.to_detail()
    payload = pin.product_pin_payload(detail)
    # Launch / drip UTM variant
    if kind == "launch":
        payload["link"] = payload["link"].replace(
            "utm_campaign=pin", "utm_campaign=launch_pin"
        )
    else:
        payload["link"] = payload["link"].replace(
            "utm_campaign=pin", "utm_campaign=auto_pin"
        )

    if kind == "drip":
        _rotate_image(db, product, detail, payload)

    if not payload.get("image_url"):
        _record(
            db,
            product=product,
            board_id=board_id or "",
            pin_id="",
            kind=kind,
            status="failed",
            error="missing_image_url",
        )
        return {"ok": False, "error": "missing_image_url", "slug": product.slug}

    bid = (board_id or board_id_for_category(product.category)).strip()
    if not bid:
        return {"ok": False, "error": "no_board_id", "slug": product.slug}

    try:
        created = await pin.create_pin(
            board_id=bid,
            title=payload["title"],
            description=payload["description"],
            link=payload["link"],
            image_url=payload["image_url"],
            alt_text=payload["alt_text"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pin create failed slug=%s kind=%s", product.slug, kind)
        _record(
            db,
            product=product,
            board_id=bid,
            pin_id="",
            kind=kind,
            status="failed",
            error=str(exc)[:2000],
        )
        return {"ok": False, "error": str(exc), "slug": product.slug, "board_id": bid}

    pin_id = str(created.get("id") or "")
    _record(
        db,
        product=product,
        board_id=bid,
        pin_id=pin_id,
        kind=kind,
        status="active",
    )
    return {
        "ok": True,
        "slug": product.slug,
        "kind": kind,
        "board_id": bid,
        "pin_id": pin_id,
        "title": payload["title"],
        "link": payload["link"],
    }


async def pin_product_launch(db: Session, product: Product) -> dict[str, Any]:
    """One-shot pin when a product is newly imported."""
    if not launch_pin_enabled():
        return {"ok": False, "skipped": True, "reason": "launch_disabled"}
    if already_launch_pinned(db, product.slug):
        return {"ok": False, "skipped": True, "reason": "already_launch_pinned", "slug": product.slug}

    # Category board (primary) + optional second pin on shop board if different.
    results: list[dict[str, Any]] = []
    cat_board = board_id_for_category(product.category)
    r1 = await create_product_pin(db, product, kind="launch", board_id=cat_board)
    results.append(r1)

    also_shop = _env_bool("PINTEREST_LAUNCH_ALSO_SHOP", True)
    shop = shop_board_id()
    if also_shop and shop and shop != cat_board and r1.get("ok"):
        r2 = await create_product_pin(db, product, kind="launch", board_id=shop)
        results.append(r2)

    ok_any = any(r.get("ok") for r in results)
    return {"ok": ok_any, "results": results, "slug": product.slug}


def select_drip_candidates(db: Session, *, limit: int) -> list[Product]:
    """Active products not pinned within cooldown, never-pinned first."""
    if limit <= 0:
        return []
    cutoff = _utcnow() - timedelta(days=repin_cooldown_days())
    products = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.id.asc())
        .all()
    )
    scored: list[tuple[bool, datetime, Product]] = []
    for p in products:
        if not (p.image_url or "").strip() and not p.active_variants():
            continue
        # Need some image eventually
        detail = p.to_public()
        if not detail.get("image_url"):
            continue
        last = last_successful_pin_at(db, p.slug)
        if last is not None and last >= cutoff:
            continue
        never = last is None
        scored.append((not never, last or datetime.min, p))

    if not scored:
        return []
    random.shuffle(scored)
    scored.sort(key=lambda s: (s[0], s[1]))  # never-pinned first, then oldest
    return [s[2] for s in scored[:limit]]


def _reauth_marker() -> Path:
    """One-notice-per-day marker, kept next to the token file."""
    return pin.token_path().with_name(".pinterest_reauth_notice")


def _notified_today() -> bool:
    try:
        return _reauth_marker().read_text(encoding="utf-8").strip() == date.today().isoformat()
    except OSError:
        return False


def _mark_notified_today() -> None:
    try:
        marker = _reauth_marker()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(date.today().isoformat(), encoding="utf-8")
    except OSError:
        # Worst case we send one extra email — never break the drip over this.
        logger.warning("could not write reauth marker")


async def check_token_health(*, notify: bool = True) -> dict[str, Any]:
    """Email a warning before the refresh token dies.

    The access token refreshes itself, but the refresh token has a hard
    deadline that only a manual OAuth round trip resets. Without this the
    whole pipeline just starts returning 401s one morning with no warning.
    """
    health = pin.token_health()
    if not pin.is_configured():
        return health

    urgent = bool(health.get("reauth_required"))
    warning = bool(health.get("reauth_warning"))
    health["notified"] = False
    if not (urgent or warning):
        return health

    if urgent:
        logger.error("pinterest refresh token expired — re-OAuth required")
    else:
        logger.warning(
            "pinterest refresh token expires in %s days",
            health.get("refresh_expires_in_days"),
        )

    if not notify or _notified_today():
        return health

    from services import email as mail

    if not mail.configured():
        logger.warning("pinterest re-auth needed but SMTP is not configured")
        return health

    recipients = mail._notify_owner()
    if not recipients:
        return health

    days = health.get("refresh_expires_in_days")
    if urgent:
        subject = "Pinterest disconnected — auto-pin is down"
        headline = (
            "The Pinterest refresh token has expired. Auto-pin and launch pins "
            "are failing until the account is reconnected."
        )
    else:
        subject = f"Pinterest: reconnect within {days} days"
        headline = (
            f"The Pinterest refresh token expires in {days} days. When it does, "
            "auto-pin stops until you reconnect by hand."
        )

    body = (
        f"{headline}\n\n"
        "Fix (about two minutes):\n"
        "  1. Open a private browser window, log in as The Books Wanderer.\n"
        f"  2. Visit {pin.public_base()}/api/pinterest/oauth/start?admin_key=YOUR_SECRET_KEY\n"
        "  3. Approve the permissions.\n\n"
        "Then confirm:\n"
        "  cd /var/www/thebookswanderer.com/server\n"
        "  .venv/bin/python scripts/pinterest_cli.py whoami\n"
    )

    try:
        sent = await mail.send_email(to=recipients, subject=subject, text=body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not send pinterest re-auth warning: %s", exc)
        return health

    if sent:
        health["notified"] = True
        _mark_notified_today()
    return health


async def run_daily_drip(*, limit: int | None = None) -> dict[str, Any]:
    """Pick products and pin them (default 1/day)."""
    from database import SessionLocal, init_db

    if not auto_pin_enabled():
        return {"ok": True, "skipped": True, "reason": "auto_disabled"}

    # Runs first: if the refresh token is about to die we want the warning out
    # even on a day with no candidates to pin.
    token = await check_token_health()

    n = pins_per_day() if limit is None else limit
    init_db()
    db = SessionLocal()
    try:
        candidates = select_drip_candidates(db, limit=n)
        if not candidates:
            return {
                "ok": True,
                "pinned": [],
                "message": "no_candidates",
                "token": token,
            }
        out: list[dict[str, Any]] = []
        for product in candidates:
            board = board_id_for_category(product.category)
            result = await create_product_pin(
                db, product, kind="drip", board_id=board
            )
            out.append(result)
            logger.info(
                "drip pin slug=%s ok=%s pin_id=%s",
                product.slug,
                result.get("ok"),
                result.get("pin_id"),
            )
        return {
            "ok": all(r.get("ok") for r in out) if out else True,
            "pinned": out,
            "count": len(out),
            "token": token,
        }
    finally:
        db.close()
