"""
Canonical storefront categories.

Store `Product.category` as the slug (e.g. "book-accessories").
Display names are English (site locale).
"""
from __future__ import annotations

from typing import Any

# Primary taxonomy — keep slugs stable; rename display freely.
# `intro` paragraphs power collection landing pages (SEO body copy).
CATEGORIES: list[dict[str, Any]] = [
    {
        "slug": "book-accessories",
        "name": "Book accessories",
        "h1": "Book accessories for everyday reading",
        "description": "Page holders, bookmarks, clips, and tools for physical books.",
        "meta_description": (
            "Bookmarks, page holders, clips, and reading tools curated by "
            "The Books Wanderer — small pieces that keep your place and free a hand."
        ),
        "intro": [
            (
                "Physical books deserve tools that respect the page: bookmarks that "
                "do not crease, holders that free a hand for tea, and clips that mark "
                "a chapter without dog-ears. This collection gathers the pieces we "
                "actually use on paperbacks, hardcovers, and journals."
            ),
            (
                "Every item is chosen for feel and function first — wood, metal, soft "
                "silicone, and paper prints that look at home on a nightstand. Prices "
                "are in USD with clear options when a design comes in more than one finish."
            ),
            (
                "Browse the full set below, or start with a hollow bookmark, a wooden "
                "finger buckle, or a multi-pack gift set for the reader in your life."
            ),
        ],
        "tile": "linear-gradient(150deg, #2b5240, #10241a)",
        "sort_order": 1,
    },
    {
        "slug": "decor",
        "name": "Decor",
        "h1": "Reading nook decor",
        "description": "Desk ornaments and pieces that dress the reading corner.",
        "meta_description": (
            "Desk lamps, stickers, and reading-nook decor from The Books Wanderer — "
            "small atmospheric pieces for shelves and study tables."
        ),
        "intro": [
            (
                "A reading corner is more than a stack of books. Soft light, a small "
                "lamp shaped like stacked volumes, stained-glass stickers in a window — "
                "these are the details that make a desk feel like a place to stay."
            ),
            (
                "Our decor collection stays intentionally small: pieces that photograph "
                "well, ship carefully, and do not fight for attention with the story you "
                "are mid-chapter. Gift-ready packaging comes with every boutique order."
            ),
        ],
        "tile": "linear-gradient(150deg, #c1912f, #8a5f16)",
        "sort_order": 2,
    },
    {
        "slug": "ereader-accessories",
        "name": "E-reader accessories",
        "h1": "E-reader accessories for Kindle and beyond",
        "description": "Sleeves, stands, and gear for Kindle and other e-readers.",
        "meta_description": (
            "Kindle sleeves and e-reader accessories from The Books Wanderer — "
            "magnetic flaps, soft finishes, and bag-ready protection for your device."
        ),
        "intro": [
            (
                "E-readers travel: bag, beach tote, nightstand drawer. A good sleeve "
                "keeps the screen safe without adding bulk, and looks better than a "
                "generic case when you pull it out on the train."
            ),
            (
                "We curate accessories that pair with popular Kindles (and similar "
                "devices) — magnetic closures, soft exteriors, and colors that match a "
                "literary rather than tech-store aesthetic. Pair with our Amazon e-reader "
                "picks if you are still choosing a device."
            ),
        ],
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
