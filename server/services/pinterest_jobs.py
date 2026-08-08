"""Pinterest auto-pin: launch pins on new products + daily drip."""
from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

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
    db.commit()
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


async def run_daily_drip(*, limit: int | None = None) -> dict[str, Any]:
    """Pick products and pin them (default 1/day)."""
    from database import SessionLocal, init_db

    if not auto_pin_enabled():
        return {"ok": True, "skipped": True, "reason": "auto_disabled"}

    n = pins_per_day() if limit is None else limit
    init_db()
    db = SessionLocal()
    try:
        candidates = select_drip_candidates(db, limit=n)
        if not candidates:
            return {"ok": True, "pinned": [], "message": "no_candidates"}
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
        }
    finally:
        db.close()
