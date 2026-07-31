"""
Canonical storefront categories.

Store `Product.category` as the slug (e.g. "book-accessories").
Display names are English (site locale).
"""
from __future__ import annotations

from typing import Any

# Primary taxonomy — keep slugs stable; rename display freely.
CATEGORIES: list[dict[str, Any]] = [
    {
        "slug": "book-accessories",
        "name": "Book accessories",
        "description": "Page holders, bookmarks, clips, and tools for physical books.",
        "tile": "linear-gradient(150deg, #2b5240, #10241a)",
        "sort_order": 1,
    },
    {
        "slug": "decor",
        "name": "Decor",
        "description": "Desk ornaments and pieces that dress the reading corner.",
        "tile": "linear-gradient(150deg, #c1912f, #8a5f16)",
        "sort_order": 2,
    },
    {
        "slug": "ereader-accessories",
        "name": "E-reader accessories",
        "description": "Sleeves, stands, and gear for Kindle and other e-readers.",
        "tile": "linear-gradient(150deg, #a63a2f, #6d221c)",
        "sort_order": 3,
    },
]

_BY_SLUG = {c["slug"]: c for c in CATEGORIES}

# Map legacy free-text labels → slug
_LEGACY_MAP: dict[str, str] = {
    "reading accessories": "book-accessories",
    "reading rituals": "book-accessories",
    "journaling": "book-accessories",
    "collection": "book-accessories",
    "book accessories": "book-accessories",
    "decor": "decor",
    "decoration": "decor",
    "desk decor": "decor",
    "cozy atmosphere": "decor",
    "e-reader accessories": "ereader-accessories",
    "ereader accessories": "ereader-accessories",
    "sleeves & kindle": "ereader-accessories",
    "sleeves and kindle": "ereader-accessories",
    "kindle": "ereader-accessories",
}


def all_categories() -> list[dict[str, Any]]:
    return sorted(CATEGORIES, key=lambda c: c.get("sort_order", 99))


def get_category(slug: str | None) -> dict[str, Any] | None:
    if not slug:
        return None
    return _BY_SLUG.get(slug.strip().lower())


def normalize_category(value: str | None) -> str:
    """
    Return a valid category slug from stored value.
    Accepts slug or legacy display string; defaults to book-accessories.
    """
    raw = (value or "").strip()
    if not raw:
        return "book-accessories"
    key = raw.lower()
    if key in _BY_SLUG:
        return key
    mapped = _LEGACY_MAP.get(key)
    if mapped:
        return mapped
    # slug-ish unknown → keep if we later expand; else default
    slugish = key.replace(" ", "-").replace("&", "and")
    if slugish in _BY_SLUG:
        return slugish
    return "book-accessories"


def display_name(value: str | None) -> str:
    cat = get_category(normalize_category(value))
    return (cat or {}).get("name") or "Book accessories"


def public_meta(value: str | None) -> dict[str, str]:
    slug = normalize_category(value)
    cat = get_category(slug) or _BY_SLUG["book-accessories"]
    return {
        "category": cat["name"],
        "category_slug": cat["slug"],
    }
