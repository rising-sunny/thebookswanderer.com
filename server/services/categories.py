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
        "slug": "books",
        "name": "Books & journals",
        "h1": "Printed books, coloring books and reading journals",
        "description": "Coloring books, literary puzzle books and reading journals, printed to order.",
        "meta_description": (
            "Printed books from The Books Wanderer: coloring books made from old "
            "illustrations, literary mysteries, reading journals and notebooks, printed to order."
        ),
        "intro": [
            (
                "These are the books we make ourselves. Coloring books built from public "
                "domain art, from Walter Crane's fairy tales to Audubon's birds. Literary "
                "puzzles. Journals for keeping track of what you read and what you think of it."
            ),
            (
                "Each one is printed and bound to order by our book printer, so it ships "
                "new. Prices are in USD, and shipping to the United States is included."
            ),
        ],
        "guides_h": "Guides that help",
        "faq_h": "Questions",
        "guides": [
            {
                "title": "Free literary coloring pages",
                "href": "/guides/free-literary-coloring-pages/",
                "blurb": "Three free printable pages from the first editions of Alice in Wonderland and The Wizard of Oz.",
            },
            {
                "title": "Gifts for book lovers they will actually use",
                "href": "/guides/gifts-for-book-lovers/",
                "blurb": "Gift ideas by budget and by kind of reader, with Christmas order dates.",
            },
        ],
        "tile": "linear-gradient(150deg, #5b3a29, #2e1c12)",
        "sort_order": 0,
    },
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
        "guides_h": "Guides that help",
        "faq_h": "Questions",
        "guides": [
            {
                "title": "How to hold a book open with one hand",
                "href": "/guides/hold-a-book-open-one-handed/",
                "blurb": "Four easy ways, from a thumb trick to a page holder.",
            },
            {
                "title": "How to read without holding the book",
                "href": "/guides/how-to-read-hands-free/",
                "blurb": "At a table, on the sofa and in bed, from free tricks to stands.",
            },
            {
                "title": "Gifts for book lovers under $25",
                "href": "/guides/gifts-for-book-lovers-under-25/",
                "blurb": "Bookmarks, book holders and other small gifts readers use.",
            },
            {
                "title": "Stocking stuffers for book lovers",
                "href": "/guides/stocking-stuffers-for-book-lovers/",
                "blurb": "Small gifts that fit in a Christmas stocking.",
            },
        ],
        "faq": [
            {
                "q": "How do I keep a book open with one hand?",
                "a": "There are four easy ways, from a thumb trick that needs nothing to a finger page holder or a clip.",
                "link": {"href": "/guides/hold-a-book-open-one-handed/", "label": "Our guide walks through each one."},
            },
            {
                "q": "How can I read without holding the book at all?",
                "a": "At a table, put the book on a stand and clip the pages. On the sofa, use a lap stand. In bed, sit up with a lap stand on the duvet, or switch to an e-reader with a page-turner remote.",
                "link": {"href": "/guides/how-to-read-hands-free/", "label": "More in our hands-free guide."},
            },
            {
                "q": "Will a bookmark or a clip damage my pages?",
                "a": "Choose smooth or soft ones. A hollow metal bookmark slides onto the page without creasing it, and a soft silicone clip is gentle on paper. Avoid pressing the spine of a new paperback flat, because that cracks the glue.",
            },
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
        "guides_h": "Guides that help",
        "faq_h": "Questions",
        "guides": [
            {
                "title": "Gifts for book lovers they will actually use",
                "href": "/guides/gifts-for-book-lovers/",
                "blurb": "Gift ideas by budget and by kind of reader.",
            },
            {
                "title": "Gifts for Jane Austen fans",
                "href": "/guides/gifts-for-jane-austen-fans/",
                "blurb": "For readers who already own the novels.",
            },
            {
                "title": "Stocking stuffers for book lovers",
                "href": "/guides/stocking-stuffers-for-book-lovers/",
                "blurb": "Small pieces that fit in a Christmas stocking.",
            },
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
                "literary rather than tech-store aesthetic."
            ),
        ],
        "guides_h": "Guides that help",
        "faq_h": "Questions",
        "guides": [
            {
                "title": "E-reader accessories worth buying, and three to skip",
                "href": "/guides/best-ereader-accessories/",
                "blurb": "A sleeve that fits, a page-turner remote and what you can skip.",
            },
            {
                "title": "How many books does a 16 GB Kindle hold?",
                "href": "/guides/how-many-books-does-a-kindle-hold/",
                "blurb": "The math, what changes it and whether you need 32 GB.",
            },
            {
                "title": "How to read without holding the book",
                "href": "/guides/how-to-read-hands-free/",
                "blurb": "Including an e-reader with a page-turner remote in bed.",
            },
            {
                "title": "Gifts for Kindle readers that aren't books",
                "href": "/guides/gifts-for-kindle-readers/",
                "blurb": "A sleeve, a reading journal, a stand and more.",
            },
        ],
        "faq": [
            {
                "q": "What size Kindle sleeve do I need?",
                "a": "Our Kindle Magnetic Sleeve comes in four sizes: 6 inch, 6.8 inch, 7 inch and 10.2 inch for the Kindle Scribe. Pick the one that matches your device's screen size, which is in the device's specifications.",
            },
            {
                "q": "Can I turn pages without touching my e-reader?",
                "a": "Yes. The Kindle Page Turner Remote has a clip that goes on the edge of the screen and taps it when you press the button on the remote. It uses no Bluetooth, no wifi and no app. It works with Kindle, Kobo, phones and tablets with a touch screen, for devices up to 0.45 in (1.1 cm) thick, case included. Some older Kindle models do not work, and the product page lists them.",
                "link": {"href": "/products/kindle-page-turner-remote", "label": "See the page turner remote."},
            },
            {
                "q": "How many books fit on a Kindle?",
                "a": "A 16 GB Kindle usually holds 4,000 to 10,000 novels.",
                "link": {"href": "/guides/how-many-books-does-a-kindle-hold/", "label": "The math is in our guide."},
            },
            {
                "q": "How can I read in bed without holding the device?",
                "a": "With the page turner remote you can keep your hands under the blanket and still turn pages. For other setups, such as a stand at a table or on your lap, see our guide.",
                "link": {"href": "/guides/how-to-read-hands-free/", "label": "Read the hands-free guide."},
            },
        ],
        "tile": "linear-gradient(150deg, #a63a2f, #6d221c)",
        "sort_order": 3,
    },
    {
        "slug": "printables",
        "name": "Printables",
        "h1": "Printable reading journals and bookish downloads",
        "description": "Instant-download reading journals and trackers to print at home.",
        "meta_description": (
            "Printable reading journals from The Books Wanderer — instant PDF downloads "
            "in A4, Letter and A5, designed to print at home and fold into a booklet."
        ),
        "intro": [
            (
                "Some reading companions do not need a parcel. Our printables are PDF "
                "downloads you buy once, print at home or at a copy shop, and fold into "
                "a booklet — no shipping, no waiting, delivered to your inbox right after checkout."
            ),
            (
                "Each one is designed from scratch rather than resold from a template pack, "
                "with print guides for A4 and US Letter and an A5 version for ring binders "
                "and tablets."
            ),
        ],
        "guides_h": "Guides that help",
        "faq_h": "Questions",
        "guides": [
            {
                "title": "The 2027 Reading Challenge",
                "href": "/reading-challenge-2027/",
                "blurb": "52 free prompts, one a week, with an optional free printable.",
            },
            {
                "title": "How to read 52 books in a year",
                "href": "/guides/how-to-read-52-books-in-a-year/",
                "blurb": "About 50 minutes a day, and a calculator for your own pace.",
            },
            {
                "title": "2027 reading challenges, compared",
                "href": "/guides/2027-reading-challenges-compared/",
                "blurb": "How the main challenges differ and how to pick one.",
            },
        ],
        "faq": [
            {
                "q": "What do I get after paying?",
                "a": "A digital download. The link arrives by email right after payment, and nothing is shipped.",
            },
            {
                "q": "What paper sizes do the printables come in?",
                "a": "The reading journals come as PDFs in A4, Letter and A5, designed to print at home and fold into a booklet. Our kits come in US Letter and A4.",
            },
            {
                "q": "Can I use them on a tablet?",
                "a": "Yes. Print them on plain paper, or fill them in with GoodNotes, Notability or any PDF app on a tablet. They are for personal use.",
            },
        ],
        "tile": "linear-gradient(150deg, #3a4f7a, #1b2540)",
        "sort_order": 4,
    },
    {
        "slug": "mathrelaxing",
        "name": "MathRelaxing",
        "h1": "MathRelaxing: mathematics you can hold",
        "description": "Math art prints, gifts and printables from our sister studio MathRelaxing.",
        "meta_description": (
            "MathRelaxing at The Books Wanderer — fractals, curves and famous equations "
            "drawn from their formulas, on posters, mugs, bookmarks and printables."
        ),
        "intro": [
            (
                "MathRelaxing is our sister studio for readers who also love a good equation. "
                "Every design is computed from real mathematics — a Julia set, Euler's identity, "
                "a standing wave — and set with the same care we give a book page."
            ),
            (
                "Physical pieces are printed to order by our production partners; printables "
                "are PDF downloads delivered right after checkout. Prices are in USD."
            ),
        ],
        "guides_h": "Guides that help",
        "faq_h": "Questions",
        "guides": [
            {
                "title": "Gifts for math lovers",
                "href": "/guides/gifts-for-math-lovers/",
                "blurb": "Posters of famous equations, an Euler's identity mug and more.",
            },
        ],
        "faq": [
            {
                "q": "What is MathRelaxing?",
                "a": "It is the math art studio of The Books Wanderer. Its designs are fractals, curves and famous equations drawn from their formulas, on posters, mugs, bookmarks and printables.",
            },
            {
                "q": "Are the designs made from stock images?",
                "a": "No. They are computed from real mathematics, not stock art.",
            },
        ],
        "tile": "linear-gradient(150deg, #1f3b57, #0d1b2a)",
        "sort_order": 5,
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
    "books": "books",
    "books & journals": "books",
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
