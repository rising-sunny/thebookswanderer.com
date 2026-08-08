"""Canonical public URLs for SEO (pretty paths preferred over query strings)."""
from __future__ import annotations

import os
from urllib.parse import quote

PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "https://thebookswanderer.com").rstrip("/")


def product_path(slug: str) -> str:
    s = (slug or "").strip()
    if not s:
        return "/#featured"
    return f"/products/{quote(s, safe='-_.~')}"


def product_url(slug: str, *, base: str | None = None) -> str:
    root = (base or PUBLIC_BASE).rstrip("/")
    return f"{root}{product_path(slug)}"


def pick_path(slug: str) -> str:
    s = (slug or "").strip()
    if not s:
        return "/#ereaders"
    return f"/picks/{quote(s, safe='-_.~')}"


def pick_url(slug: str, *, base: str | None = None) -> str:
    root = (base or PUBLIC_BASE).rstrip("/")
    return f"{root}{pick_path(slug)}"


def collection_path(slug: str) -> str:
    s = (slug or "").strip()
    if not s:
        return "/collections"
    return f"/collections/{quote(s, safe='-_.~')}"


def collection_url(slug: str, *, base: str | None = None) -> str:
    root = (base or PUBLIC_BASE).rstrip("/")
    return f"{root}{collection_path(slug)}"
