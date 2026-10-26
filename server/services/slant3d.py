"""Slant 3D print farm (API v2) for 3D printed products.

SLANT3D_API_KEY (sl_...) is sent as a Bearer token. SLANT3D_PLATFORM_ID names the
platform that files and orders belong to; it is created once on the Slant 3D
account page. Orders are charged to the account card when they are processed,
so the pass-through keeps POST /orders behind TBW_SUPPLIER_ORDERS_ENABLED.
"""
from __future__ import annotations

import os

BASE = "https://slant3dapi.com/v2/api"
SUPPLIER = "slant3d"


class Slant3DError(RuntimeError):
    """Safe operational message; no upstream bodies or credentials."""


def key() -> str:
    value = (os.getenv("SLANT3D_API_KEY") or "").strip()
    if not value or "\n" in value or "\r" in value:
        raise Slant3DError("Slant 3D is not configured")
    return value


def configured() -> bool:
    try:
        return bool(key())
    except Slant3DError:
        return False


def platform_id() -> str:
    return (os.getenv("SLANT3D_PLATFORM_ID") or "").strip()


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer " + key(), "User-Agent": "TheBooksWanderer"}
