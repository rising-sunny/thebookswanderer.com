"""Digital products: where the files live and who may download them.

Files sit in DIGITAL_DIR, outside the web root, and are only ever served by
/api/download/<token>. A paid order gets one token per digital line; each
token expires after DIGITAL_LINK_DAYS and allows DIGITAL_MAX_DOWNLOADS uses,
so a forwarded link stops working after a while.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SUPPLIER = "digital"


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def digital_dir() -> Path:
    return Path(_env("DIGITAL_DIR", "/var/lib/tbw-digital"))


def link_days() -> int:
    return int(_env("DIGITAL_LINK_DAYS", "30"))


def max_downloads() -> int:
    return int(_env("DIGITAL_MAX_DOWNLOADS", "10"))


def is_digital(product: Any) -> bool:
    return (getattr(product, "supplier", "") or "") == SUPPLIER


_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.(pdf|zip|png|jpg|epub)$")


def safe_name(name: str) -> str | None:
    """A bare file name we are willing to store and serve, or None."""
    name = (name or "").strip()
    return name if _SAFE.match(name) else None


def file_path(name: str) -> Path | None:
    name = safe_name(name) or ""
    if not name:
        return None
    path = digital_dir() / name
    return path if path.is_file() else None


def file_for(product: Any, variant: Any | None) -> str:
    return (getattr(variant, "digital_file", "") or "") or (product.digital_file or "")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def expiry() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=link_days())


def order_key(order_id: int) -> str:
    """Short signature that lets the checkout page fetch an order's links."""
    secret = _env("SECRET_KEY", "")
    return hmac.new(secret.encode(), f"order:{order_id}".encode(), hashlib.sha256).hexdigest()[:24]


def check_order_key(order_id: int, key: str | None) -> bool:
    return bool(key) and hmac.compare_digest(order_key(order_id), key or "")


def download_url(base: str, token: str) -> str:
    return f"{base.rstrip('/')}/api/download/{token}"
