"""
The Books Wanderer — store API
Static site + FastAPI (CJ Dropshipping + PayPal), same VPS pattern as mathrelaxing.store.
"""
from __future__ import annotations

import logging
import math
import hashlib
import hmac
import json
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote as url_quote

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).resolve().parent / ".env")

from database import get_db, init_db  # noqa: E402
from models import DownloadToken, Order, OrderItem, Product, ProductVariant  # noqa: E402
from services import digital as digital_service  # noqa: E402
from services import categories as cat_service  # noqa: E402
from services import cj as cj_service  # noqa: E402
from services import email as email_service  # noqa: E402
from services import paypal as paypal_service  # noqa: E402
from services import paypal_recovery  # noqa: E402
from services import printify as printify_service  # noqa: E402
from services import lulu as lulu_service  # noqa: E402
from services import lulu_submission  # noqa: E402
from services import prodigi_store, prodigi_submission  # noqa: E402
from services import pricing as pricing_service  # noqa: E402
from services import shipping as shipping_service  # noqa: E402
from services.countries import DESTINATIONS  # noqa: E402
from ssr import (  # noqa: E402
    affiliate_by_slug,
    render_catalog_page,
    inject_home_seo,
    load_affiliate_catalog,
    render_collection_not_found,
    render_collection_page,
    render_collections_index,
    render_pick_not_found,
    render_pick_page,
    render_product_not_found,
    render_product_page,
)
from urls import (  # noqa: E402
    PUBLIC_BASE,
    collection_url,
    pick_path,
    pick_url,
    product_path,
    product_url,
)
from live import router as live_router  # noqa: E402
import i18n  # noqa: E402
from routers.pinterest import router as pinterest_router  # noqa: E402
from routers.collaborators import router as collaborators_router  # noqa: E402
from routers.outreach import router as outreach_router  # noqa: E402

# Standard US shipping is included in existing prices. International delivery
# is quoted live and may add a surcharge over the same basket's US cost.
FREE_SHIPPING = (os.getenv("FREE_SHIPPING", "1") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


log = logging.getLogger("tbw.shop")

# What the shopper sees when the fulfilment provider cannot quote freight.
# The provider's own error is logged, never returned: it can name the supplier
# and expose operational detail that has no place in a storefront.
SHIPPING_UNAVAILABLE_MSG = (
    "We can't calculate delivery for this address right now. It's a problem on "
    "our side, not with your details. Please try again in a few minutes, or "
    "email hello@thebookswanderer.com and we'll complete the order for you."
)


def _log_freight_failure(exc: Exception, *, origin: str, country: str) -> None:
    """Record the provider's real error where the owner can find it."""
    log.error("freight quote failed %s -> %s: %s", origin, country, exc)


CJ_PAY_TYPE = int(os.getenv("CJ_PAY_TYPE", "3"))
# How much dearer a carrier may be before we stop trading money for speed.
# CJ's cheapest line is not always the sane pick: to Malaysia it is $1.89 for
# 15-30 days when $4.26 buys 4-5 days. To the US the cheapest already is the
# fastest, so this changes nothing there.
SHIP_UPGRADE_MAX_USD = float(os.getenv("SHIPPING_UPGRADE_MAX_USD", "3.0"))

app = FastAPI(title="The Books Wanderer API", version="0.1.0")
app.include_router(live_router)
app.include_router(pinterest_router)
app.include_router(collaborators_router)
app.include_router(outreach_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        PUBLIC_BASE,
        "https://www.thebookswanderer.com",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    from services import collaborators_store
    try:
        collaborators_store.init_store()
        collaborators_store.seed_sources()
    except (OSError, sqlite3.Error):
        # A research-storage issue must not take checkout or the storefront down.
        log.error("Collaborator research storage unavailable; check its private directory permissions")


# ── Schemas ──────────────────────────────────────────────────────────


class CartItemIn(BaseModel):
    product_id: int
    variant_id: int | None = None  # required when product has variants
    quantity: int = Field(ge=1, le=20)


class ShippingQuoteIn(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    zip_code: str | None = None
    city: str = Field("", max_length=80)
    state: str = Field("", max_length=80)
    street1: str = Field("", max_length=200)
    street2: str = Field("", max_length=200)
    phone_number: str = Field("", max_length=30)
    recipient_tax_id: str = Field("", max_length=80)
    items: list[CartItemIn]


class CheckoutIn(BaseModel):
    email: EmailStr
    customer_name: str = Field(min_length=2, max_length=80)
    phone: str = ""
    recipient_tax_id: str = Field("", max_length=80)
    # Address fields are checked in checkout(): a cart of digital downloads
    # has nothing to ship, so they may be empty.
    shipping_address: str = Field("", max_length=200)
    shipping_address2: str = ""
    shipping_city: str = Field("", max_length=80)
    shipping_province: str = Field("", max_length=80)
    shipping_zip: str = ""
    shipping_country: str = Field(min_length=2, max_length=80)
    shipping_country_code: str = Field(min_length=2, max_length=2)
    items: list[CartItemIn]
    logistic_name: str = ""
    shipping_total: float | None = None  # client can pass quote; revalidated server-side
    expected_total: float | None = None
    lang: str = "en"


class AddProductIn(BaseModel):
    """Admin: list a CJ product (all variants imported as selectable options)."""

    cj_pid: str
    cj_vid: str | None = None  # optional default variant
    title: str | None = None
    description: str | None = None
    category: str = ""
    price_usd: float | None = None  # retail for all variants if set
    slug: str | None = None
    admin_key: str


class DraftIn(BaseModel):
    """Internal: hidden draft of a CJ product for the restricted admin API."""

    cj_pid: str = Field(pattern=r"^[A-Za-z0-9-]{1,64}$")
    cj_vid: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,64}$")
    title: str | None = Field(default=None, min_length=3, max_length=300)
    category: str = Field(default="", max_length=120)
    price_usd: float | None = Field(default=None, gt=0, le=10000)


class DraftUpdateIn(BaseModel):
    """Internal: edit a hidden draft before publication."""

    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    title_es: str | None = Field(default=None, min_length=3, max_length=300)
    description_es: str | None = Field(default=None, min_length=1, max_length=5000)
    category: str | None = Field(default=None, max_length=120)
    price_usd: float | None = Field(default=None, gt=0, le=10000)  # all variants


class DraftPublishIn(BaseModel):
    """Internal: the code shown by the publication preview."""

    code: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")
    pin: bool = False  # launch pin on Pinterest, same as an admin import


class ConfirmIn(BaseModel):
    """Internal: the code shown by an unpublish preview."""

    code: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")


class InternalQuoteIn(BaseModel):
    """Internal: shipping quote for a live product or a draft."""

    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    variant_id: int | None = Field(default=None, ge=1)
    quantity: int = Field(default=1, ge=1, le=20)


class PageIn(BaseModel):
    page: int = Field(default=1, ge=1, le=100)
    limit: int = Field(default=20, ge=1, le=50)


class ShipOrderIn(BaseModel):
    """Admin: mark order shipped and email the customer with tracking."""

    admin_key: str
    order_id: int
    tracking_number: str = ""
    tracking_url: str = ""
    carrier: str = ""
    send_email: bool = True


class CartReminderIn(BaseModel):
    """Optional abandoned-cart email (you supply the address + line summary)."""

    admin_key: str
    email: EmailStr
    customer_name: str = ""
    lines: list[dict] = Field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (s or "product")[:100]


def _admin_ok(key: str) -> bool:
    expected = os.getenv("SECRET_KEY", "")
    return bool(expected) and key == expected


def _pick_variant(details: dict, preferred_vid: str | None) -> dict:
    variants = details.get("variants") or []
    if not variants:
        raise HTTPException(400, "CJ product has no variants")
    if preferred_vid:
        for v in variants:
            if str(v.get("vid")) == preferred_vid:
                return v
    return variants[0]


def _resolve_variant(db: Session, product: Product, variant_id: int | None) -> ProductVariant | None:
    variants = product.active_variants()
    if not variants:
        return None
    if variant_id:
        for v in variants:
            if v.id == variant_id:
                return v
        raise HTTPException(400, f"Invalid variant {variant_id} for product {product.id}")
    return variants[0]


def _load_cart_lines(
    db: Session, items: list[CartItemIn]
) -> list[tuple[Product, ProductVariant | None, int]]:
    if not items:
        raise HTTPException(400, "Cart is empty")
    out: list[tuple[Product, ProductVariant | None, int]] = []
    for line in items:
        p = db.get(Product, line.product_id)
        if not p or not p.active:
            raise HTTPException(404, f"Product {line.product_id} not found")
        v = _resolve_variant(db, p, line.variant_id)
        out.append((p, v, line.quantity))
    return out


# ── Public: health & catalog ──────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "paypal": paypal_service.configured(),
        "cj_key_set": bool(os.getenv("CJ_API_KEY")),
        "email": email_service.configured(),
        "pricing": pricing_service.pricing_config(),
    }


@app.get("/api/pricing/preview")
def pricing_preview(cost_usd: float = Query(..., ge=0)):
    """Debug helper: cost → retail breakdown (no auth; no secrets)."""
    return pricing_service.breakdown(cost_usd).as_dict()


@app.get("/api/categories")
def list_categories(db: Session = Depends(get_db)):
    """Canonical categories with live product counts."""
    rows = db.query(Product).filter(Product.active.is_(True)).all()
    counts: dict[str, int] = {c["slug"]: 0 for c in cat_service.all_categories()}
    for p in rows:
        slug = cat_service.normalize_category(p.category)
        counts[slug] = counts.get(slug, 0) + 1
    categories = []
    for c in cat_service.all_categories():
        categories.append(
            {
                "slug": c["slug"],
                "name": c["name"],
                "description": c["description"],
                "tile": c.get("tile") or "",
                "product_count": counts.get(c["slug"], 0),
            }
        )
    return {"categories": categories, "count": len(categories)}


@app.get("/api/products")
def list_products(
    category: str | None = Query(None, description="Category slug filter"),
    lang: str = Query("en"),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.id.desc())
        .all()
    )
    filter_slug = None
    if category and category.strip():
        raw = category.strip().lower()
        known = {c["slug"] for c in cat_service.all_categories()}
        filter_slug = raw if raw in known else cat_service.normalize_category(raw)
        rows = [
            p
            for p in rows
            if cat_service.normalize_category(p.category) == filter_slug
        ]

    return {
        "products": [i18n.product(p.to_public(), lang) for p in rows],
        "count": len(rows),
        "category": filter_slug,
    }


@app.get("/api/products/by-slug/{slug}")
async def get_product_by_slug(slug: str, lang: str = Query("en"), db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.slug == slug, Product.active.is_(True)).first()
    if not p:
        raise HTTPException(404, "Product not found")
    await _ensure_product_media(p, db)
    return _with_ship_only(p, i18n.product(p.to_detail(), lang))


def _with_ship_only(p: Product, detail: dict) -> dict:
    """Legacy field retained for clients; coverage now comes from live quotes."""
    from ssr import _supplier_countries

    only = None if p.supplier == "digital" else _supplier_countries(p.supplier, p.from_country)
    detail["ship_only"] = sorted(only) if only else None
    return detail


# ── SEO: pretty URLs, 301 from query shells, dynamic sitemap ──


def _iso_date(dt: datetime | None) -> str:
    if not dt:
        return datetime.now(timezone.utc).date().isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def _file_mtime_iso(*candidates: Path) -> str:
    for p in candidates:
        try:
            if p.is_file():
                return datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc
                ).date().isoformat()
        except OSError:
            continue
    return datetime.now(timezone.utc).date().isoformat()


@app.api_route("/product.html", methods=["GET", "HEAD"])
async def product_page_legacy(
    slug: str | None = Query(None),
    id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Legacy query URL → permanent redirect to /products/{slug}."""
    p: Product | None = None
    if slug and slug.strip():
        p = (
            db.query(Product)
            .filter(Product.slug == slug.strip(), Product.active.is_(True))
            .first()
        )
    elif id:
        cand = db.get(Product, id)
        if cand and cand.active:
            p = cand
    if not p:
        return HTMLResponse(render_product_not_found(slug or ""), status_code=404)
    return RedirectResponse(url=product_path(p.slug), status_code=301)


def _related_products(product: Product, db: Session, *, limit: int = 4) -> list[dict]:
    """Siblings for the PDP's "You may also like" block.

    Product pages otherwise link to nothing but nav and footer, which leaves
    every PDP a dead end for crawlers and shoppers alike.

    Selection walks a ring: each product links to the ones that follow it in
    id order, wrapping around. Picking "newest N" instead would funnel every
    link into the same few products and starve the rest.
    """
    everything = (
        db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all()
    )
    if len(everything) < 2:
        return []

    def ring_from(pool: list[Product]) -> list[Product]:
        """Products after `product` in `pool`, wrapping to the start."""
        if not pool:
            return []
        after = [c for c in pool if c.id > product.id]
        before = [c for c in pool if c.id < product.id]
        return after + before

    same = [c for c in everything if c.category == product.category]
    other = [c for c in everything if c.category != product.category]

    picked: list[Product] = []
    seen: set[int] = {product.id}
    # Same category first, then the rest so a thin category still fills the row.
    for candidate in ring_from(same) + ring_from(other):
        if candidate.id in seen:
            continue
        card_ok = (candidate.image_url or "").strip() or candidate.active_variants()
        if not card_ok:
            continue
        seen.add(candidate.id)
        picked.append(candidate)
        if len(picked) >= limit:
            break

    out: list[dict] = []
    for candidate in picked:
        card = candidate.to_public()
        if card.get("image_url"):
            out.append(card)
    return out


@app.get("/es/products/", response_class=HTMLResponse)
@app.get("/products/", response_class=HTMLResponse)
def catalog_index(request: Request, db: Session = Depends(get_db)):
    """The full catalogue on one page.

    Registered before /products/{slug} so the bare path is not swallowed as a
    slug. Every "shop all" link points here; they used to point at the
    #featured anchor on the home page, which left the store with no browsable
    URL of its own.
    """
    rows = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.id.desc())
        .all()
    )
    lang = i18n.lang_of(request.url.path)
    products = [i18n.product(p.to_public(), lang) for p in rows]
    counts: dict[str, int] = {c["slug"]: 0 for c in cat_service.all_categories()}
    for p in rows:
        slug = cat_service.normalize_category(p.category)
        counts[slug] = counts.get(slug, 0) + 1
    categories = [
        i18n.category({**c, "product_count": counts.get(c["slug"], 0)}, lang)
        for c in cat_service.all_categories()
    ]
    canonical = i18n.url_for("/products/", lang)
    page = render_catalog_page(products, categories, canonical=canonical)
    return HTMLResponse(i18n.localize(page, lang, "/products/"))


@app.get("/es/products/{slug}", response_class=HTMLResponse)
@app.get("/products/{slug}", response_class=HTMLResponse)
async def product_page_pretty(slug: str, request: Request, variant: str | None = None,
                              db: Session = Depends(get_db)):
    """Canonical product PDP (SSR)."""
    lang = i18n.lang_of(request.url.path)
    p = db.query(Product).filter(Product.slug == slug, Product.active.is_(True)).first()
    if not p:
        # A retired product still has pins and search results pointing at it;
        # send those visitors to its collection instead of a dead end.
        gone = db.query(Product).filter(Product.slug == slug).first()
        if gone and gone.category:
            return RedirectResponse(
                url=i18n.url_for(collection_url(cat_service.normalize_category(gone.category))[len(PUBLIC_BASE):], lang),
                status_code=301,
            )
        return HTMLResponse(render_product_not_found(slug), status_code=404)
    await _ensure_product_media(p, db)
    detail = i18n.product(p.to_detail(), lang)
    path = product_path(p.slug)
    canonical = i18n.url_for(path, lang)
    related = [i18n.product(r, lang) for r in _related_products(p, db)]
    page = render_product_page(detail, canonical=canonical, related=related,
                               variant_id=int(variant) if (variant or "").isdigit() else None)
    return HTMLResponse(i18n.localize(page, lang, path))


@app.api_route("/pick.html", methods=["GET", "HEAD"])
async def pick_page_legacy(slug: str | None = Query(None)):
    """Legacy query URL → permanent redirect to /picks/{slug}."""
    if not slug or not slug.strip():
        return HTMLResponse(render_pick_not_found(""), status_code=404)
    pick = affiliate_by_slug(slug.strip())
    if not pick:
        return HTMLResponse(render_pick_not_found(slug), status_code=404)
    return RedirectResponse(url=pick_path(pick["slug"]), status_code=301)


@app.get("/picks/{slug}", response_class=HTMLResponse)
async def pick_page_pretty(slug: str):
    """Canonical Amazon affiliate pick PDP (SSR)."""
    pick = affiliate_by_slug(slug.strip())
    if not pick:
        return HTMLResponse(render_pick_not_found(slug), status_code=404)
    canonical = pick_url(pick["slug"])
    return HTMLResponse(render_pick_page(pick, canonical=canonical))


@app.api_route("/es/", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/es/index.html", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/index.html", methods=["GET", "HEAD"], response_class=HTMLResponse)
def home_page_ssr(request: Request, db: Session = Depends(get_db)):
    """Home with crawlable product + affiliate + category cards in the HTML."""
    template_path = Path(__file__).resolve().parent.parent / "index.html"
    try:
        raw = template_path.read_text(encoding="utf-8")
    except OSError:
        return HTMLResponse("<h1>Home template missing</h1>", status_code=500)
    rows = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.id.desc())
        .all()
    )
    lang = i18n.lang_of(request.url.path)
    products = [i18n.product(p.to_public(), lang) for p in rows]
    counts: dict[str, int] = {c["slug"]: 0 for c in cat_service.all_categories()}
    for p in rows:
        counts[cat_service.normalize_category(p.category)] = (
            counts.get(cat_service.normalize_category(p.category), 0) + 1
        )
    categories = []
    for c in cat_service.all_categories():
        categories.append(i18n.category({**c, "product_count": counts.get(c["slug"], 0)}, lang))
    aff = load_affiliate_catalog()
    html_out = inject_home_seo(
        raw, products=products, affiliate=aff, categories=categories
    )
    if lang == "es":
        html_out = html_out.replace(
            '<link rel="canonical" href="https://thebookswanderer.com/">',
            '<link rel="canonical" href="https://thebookswanderer.com/es/">',
        )
        html_out = html_out.replace(
            'href="/guides/gifts-for-book-lovers/"',
            'href="/guides/regalos-pequenos-para-lectores/"',
        ).replace('href="/reading-challenge-2027/"', 'href="/reto-de-lectura-2027/"')
    return HTMLResponse(i18n.localize(html_out, lang, "/"))


@app.get("/es", include_in_schema=False)
def spanish_root():
    return RedirectResponse(url="/es/", status_code=301)


@app.get("/es/collections/", include_in_schema=False)
def spanish_collections_slash():
    return RedirectResponse(url="/es/collections", status_code=301)


@app.api_route("/es/{page}.html", methods=["GET", "HEAD"], response_class=HTMLResponse)
def spanish_static_page(page: str):
    """Spanish edition of about / contact / privacy / shipping / cart / checkout."""
    if page not in i18n.STATIC_PAGES:
        raise HTTPException(404, "Not found")
    path = Path(__file__).resolve().parent.parent / f"{page}.html"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(404, "Not found")
    raw = raw.replace(
        f'<link rel="canonical" href="https://thebookswanderer.com/{page}.html">',
        f'<link rel="canonical" href="https://thebookswanderer.com/es/{page}.html">',
    )
    return HTMLResponse(i18n.localize(raw, "es", f"/{page}.html"))


@app.get("/collections/", include_in_schema=False)
def collections_index_slash():
    # Starlette's automatic slash redirect is a 307; search engines want a 301.
    return RedirectResponse(url="/collections", status_code=301)


@app.get("/es/collections", response_class=HTMLResponse)
@app.get("/collections", response_class=HTMLResponse)
def collections_index(request: Request, db: Session = Depends(get_db)):
    """Index of all storefront collections."""
    rows = db.query(Product).filter(Product.active.is_(True)).all()
    counts: dict[str, int] = {c["slug"]: 0 for c in cat_service.all_categories()}
    for p in rows:
        s = cat_service.normalize_category(p.category)
        counts[s] = counts.get(s, 0) + 1
    lang = i18n.lang_of(request.url.path)
    categories = [
        i18n.category({**c, "product_count": counts.get(c["slug"], 0)}, lang)
        for c in cat_service.all_categories()
    ]
    canonical = i18n.url_for("/collections", lang)
    page = render_collections_index(categories, canonical=canonical)
    return HTMLResponse(i18n.localize(page, lang, "/collections"))


@app.get("/es/collections/{slug}", response_class=HTMLResponse)
@app.get("/collections/{slug}", response_class=HTMLResponse)
def collection_page(slug: str, request: Request, db: Session = Depends(get_db)):
    """Category landing page with SSR product grid + JSON-LD."""
    lang = i18n.lang_of(request.url.path)
    cat = cat_service.get_category(slug)
    if not cat:
        return HTMLResponse(render_collection_not_found(slug), status_code=404)
    cat = i18n.category(cat, lang)
    rows = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.id.desc())
        .all()
    )
    products = [
        i18n.product(p.to_public(), lang)
        for p in rows
        if cat_service.normalize_category(p.category) == cat["slug"]
    ]
    all_cats = [i18n.category(c, lang) for c in cat_service.all_categories()]
    path = collection_url(cat["slug"])[len(PUBLIC_BASE):]
    canonical = i18n.url_for(path, lang)
    page = render_collection_page(cat, products, canonical=canonical, all_cats=all_cats)
    return HTMLResponse(i18n.localize(page, lang, path))


_FEED_SKIP_COUNTRIES = {"KR"}

# Google product taxonomy ids (taxonomy-with-ids.en-US.txt), first match on
# the slug wins; otherwise the shop category decides.
_GOOGLE_CATEGORY_BY_SLUG = (
    ("color-the-classics", "784"),      # Media > Books > Print Books (coloring book)
    ("jigsaw-puzzle", "3867"),          # Toys & Games > Puzzles > Jigsaw Puzzles
    ("advent-calendar", "5359"),        # Decor > Seasonal & Holiday Decorations > Advent Calendars
    ("calendar", "927"),                # Office Supplies > Filing & Organization > Calendars, Organizers & Planners
    ("reading-passport", "961"),        # Office Supplies > ... > Paper Products > Notebooks & Notepads
    ("ornament", "3144"),               # Decor > Seasonal & Holiday Decorations > Holiday Ornaments
    ("bookends", "587"),                # Home & Garden > Decor > Bookends
    ("book-nook", "4175"),              # Hobbies & Creative Arts > Model Making > Scale Model Kits
    ("lamp", "4636"),                   # Home & Garden > Lighting > Lamps
    ("lantern", "505826"),              # Lighting > Night Lights & Ambient Lighting
    ("book-light", "4941"),             # Office Supplies > Book Accessories > Book Lights
    ("book-cover", "6176"),             # Office Supplies > Book Accessories > Book Covers
    ("reading-stand", "6175"),          # Office Supplies > Book Accessories > Book Stands & Rests
    ("book-holder", "6175"),
    ("page-holder", "6175"),
    ("stained-glass-stickers", "5989"), # Home & Garden > Decor > Window Treatments > Window Films
    ("sticker", "4054"),                # Arts & Crafts > ... > Embellishments & Trims > Decorative Stickers
    ("kindle", "4738"),                 # ... > E-Book Reader Accessories > E-Book Reader Cases
    ("bookmark", "93"),                 # Office Supplies > Book Accessories > Bookmarks
    ("book-clips", "93"),
)
_GOOGLE_CATEGORY_BY_SHOP = {
    "book-accessories": "6174",         # Office Supplies > Book Accessories
    "decor": "696",                     # Home & Garden > Decor
    "ereader-accessories": "4736",      # ... > E-Book Reader Accessories
}


def _google_category(slug: str, shop_category: str) -> str:
    for needle, gid in _GOOGLE_CATEGORY_BY_SLUG:
        if needle in slug:
            return gid
    return _GOOGLE_CATEGORY_BY_SHOP.get(shop_category, "")


def _feed_text(s: str, limit: int) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


@app.get("/api/feeds/google-products.xml")
def google_products_feed(db: Session = Depends(get_db)):
    """Product feed (Google Merchant Center format, RSS 2.0 + g: namespace)
    for free listings on Google, the Pinterest catalog and AI shopping feeds.
    One item per variant, grouped by product. Downloads are left out: free
    listings are for goods that ship."""
    from ssr import _free_shipping, _supplier_countries

    # Google won't convert USD for South Korea (it wants KRW prices), so the
    # feed leaves it out rather than carry a disapproval for every item.
    ship_all = [d["code"] for d in SHIP_DESTINATIONS if d["code"] not in _FEED_SKIP_COUNTRIES]
    items: list[str] = []
    rows = db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all()
    for p in rows:
        if digital_service.is_digital(p):
            continue
        only = _supplier_countries(p.supplier, p.from_country)
        countries = [c for c in ship_all if only is None or c in only] or sorted(only or [])
        meta = cat_service.public_meta(p.category)
        gallery = [u for u in p.gallery() if u]
        variants = p.active_variants() or [None]
        group = len(variants) > 1
        for v in variants:
            title = p.title + (f" — {v.name}" if group and v and v.name else "")
            image = (v.image_url if v and v.image_url else "") or p.image_url or (gallery[0] if gallery else "")
            if not image:
                continue
            extra = [u for u in ([p.image_url] + gallery) if u and u != image][:8]
            price = float(v.price_usd if v else p.price_usd)
            link = f"{PUBLIC_BASE}/products/{p.slug}" + (f"?variant={v.id}" if group and v else "")
            parts = [
                f"<g:id>{xml_escape(f'tbw-{p.id}-{v.id}' if v else f'tbw-{p.id}')}</g:id>",
                f"<title>{xml_escape(_feed_text(title, 150))}</title>",
                # Same shipping wording as the product page (retires older promises).
                f"<description>{xml_escape(_feed_text(shipping_service.description(p.description or '', p.supplier or 'cj'), 5000) or p.title)}</description>",
                f"<link>{xml_escape(link)}</link>",
                f"<g:image_link>{xml_escape(_abs_url(image))}</g:image_link>",
                *[f"<g:additional_image_link>{xml_escape(_abs_url(u))}</g:additional_image_link>" for u in extra],
                "<g:availability>in_stock</g:availability>",
                f"<g:price>{price:.2f} USD</g:price>",
                "<g:condition>new</g:condition>",
                "<g:identifier_exists>no</g:identifier_exists>",
                f"<g:product_type>{xml_escape(meta['category'])}</g:product_type>",
            ]
            gpc = _google_category(p.slug, meta["category_slug"])
            if gpc:
                parts.append(f"<g:google_product_category>{gpc}</g:google_product_category>")
            if group:
                parts.append(f"<g:item_group_id>tbw-{p.id}</g:item_group_id>")
            if p.supplier != "digital" and (p.supplier == "lulu" or _free_shipping()):
                for c in [c for c in countries if c == "US"]:
                    parts.append(f"<g:shipping><g:country>{c}</g:country><g:price>0.00 USD</g:price></g:shipping>")
            items.append("<item>" + "".join(parts) + "</item>")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0"><channel>'
        "<title>The Books Wanderer</title>"
        f"<link>{PUBLIC_BASE}/</link>"
        "<description>Accessories and printables for readers</description>"
        + "".join(items)
        + "</channel></rss>"
    )
    return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


def _abs_url(u: str) -> str:
    return u if u.startswith("http") else f"{PUBLIC_BASE}{u if u.startswith('/') else '/' + u}"


@app.get("/sitemap.xml")
def sitemap_xml(db: Session = Depends(get_db)):
    """Dynamic sitemap from live catalog (products + picks + collections)."""
    site_root = Path(__file__).resolve().parent.parent
    urls: list[tuple[str, str, str, str]] = []  # loc, lastmod, changefreq, priority

    rows = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.slug.asc())
        .all()
    )
    # Listing pages change when the catalogue does, not every day: a lastmod
    # that is always "today" teaches Google to ignore the field.
    newest = max((p.created_at for p in rows if p.created_at), default=None)
    listing_mod = max(_iso_date(newest), _file_mtime_iso(site_root / "index.html"))

    urls.append((f"{PUBLIC_BASE}/", listing_mod, "weekly", "1.0"))
    urls.append((f"{PUBLIC_BASE}/products/", listing_mod, "weekly", "0.9"))
    urls.append((f"{PUBLIC_BASE}/collections", listing_mod, "weekly", "0.85"))

    for c in cat_service.all_categories():
        urls.append((collection_url(c["slug"]), listing_mod, "weekly", "0.85"))

    # Guides live as static directories so nginx serves /guides/<slug>/ directly.
    for guide_dir in sorted((site_root / "guides").glob("*/index.html")):
        urls.append(
            (
                f"{PUBLIC_BASE}/guides/{guide_dir.parent.name}/",
                _file_mtime_iso(guide_dir),
                "monthly",
                "0.7",
            )
        )

    for rel, prio in (
        ("about.html", "0.6"),
        ("contact.html", "0.5"),
        ("shipping-returns.html", "0.5"),
        ("privacy.html", "0.3"),
        ("press.html", "0.4"),
        ("reading-challenge-2027/index.html", "0.7"),
        ("reto-de-lectura-2027/index.html", "0.6"),
    ):
        path = site_root / rel
        if path.is_file():
            urls.append(
                (
                    f"{PUBLIC_BASE}/{rel.removesuffix('index.html')}",
                    _file_mtime_iso(path),
                    "monthly",
                    prio,
                )
            )

    aff_path = site_root / "affiliate-products.json"
    aff_mod = _file_mtime_iso(aff_path)
    for pick in load_affiliate_catalog().get("products") or []:
        slug = (pick.get("slug") or "").strip()
        if not slug:
            continue
        urls.append((pick_url(slug), aff_mod, "weekly", "0.9"))

    for p in rows:
        urls.append(
            (
                product_url(p.slug),
                _iso_date(p.created_at),
                "weekly",
                "0.8",
            )
        )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    # Pages with a Spanish edition are listed in both languages, each entry
    # naming its alternates so Google pairs them up.
    expanded: list[tuple[str, str, str, str, list[tuple[str, str]]]] = []
    for loc, lastmod, freq, prio in urls:
        path = loc[len(PUBLIC_BASE):] if loc.startswith(PUBLIC_BASE) else loc
        if i18n.is_localized(path):
            alts = [("en", i18n.url_for(path, "en")), ("es", i18n.url_for(path, "es")),
                    ("x-default", i18n.url_for(path, "en"))]
            expanded.append((loc, lastmod, freq, prio, alts))
            expanded.append((i18n.url_for(path, "es"), lastmod, freq, prio, alts))
        else:
            expanded.append((loc, lastmod, freq, prio, []))
    for loc, lastmod, freq, prio, alts in expanded:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        for hl, href in alts:
            lines.append(f'    <xhtml:link rel="alternate" hreflang="{hl}" href="{xml_escape(href)}"/>')
        lines.append(f"    <lastmod>{xml_escape(lastmod)}</lastmod>")
        lines.append(f"    <changefreq>{freq}</changefreq>")
        lines.append(f"    <priority>{prio}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    body = "\n".join(lines) + "\n"
    return Response(
        content=body,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/products/{product_id}")
async def get_product(product_id: int, lang: str = Query("en"), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p or not p.active:
        raise HTTPException(404, "Product not found")
    await _ensure_product_media(p, db)
    return _with_ship_only(p, i18n.product(p.to_detail(), lang))


async def _ensure_product_media(p: Product, db: Session) -> None:
    """Optional light refresh of missing hero image only — never paste CJ HTML dumps."""
    if p.image_url or not p.cj_pid:
        return
    try:
        details = await cj_service.get_product_details(pid=p.cj_pid)
    except cj_service.CJError:
        return
    for v in details.get("variants") or []:
        if str(v.get("vid")) == str(p.cj_vid) and v.get("variantImage"):
            p.image_url = str(v["variantImage"])
            db.commit()
            return
    if details.get("bigImage"):
        p.image_url = str(details["bigImage"])
        db.commit()


# ── Shipping destinations (curated; availability checked per quote) ───

# All countries and territories can be checked; each provider must confirm
# availability for the actual product, variant, quantity and address.
SHIP_DESTINATIONS: list[dict[str, str]] = DESTINATIONS


def _pick_freight(options: list[dict]) -> dict:
    """Fulfil using the same method selection used by customer quotations."""
    return shipping_service.pick_freight(options)


@app.get("/api/shipping/destinations")
def shipping_destinations():
    return {"destinations": SHIP_DESTINATIONS}


@app.get("/api/geo/country")
def geo_country(request: Request):
    """Best-effort country for prefilling the checkout selector.

    Returns null unless the visitor resolves to a market we actually ship to.
    Guessing wrong is worse than not guessing: the selector drives the freight
    quote, so a bad prefill shows a total for the wrong country.
    """
    from services import geo as geo_service

    ip = geo_service.extract_client_ip(request) or ""
    code = (geo_service.lookup(ip).get("country") or "").upper()
    known = {d["code"] for d in SHIP_DESTINATIONS}
    return {"country": code if code in known else None}


@app.get("/api/products/{product_id}/shipping")
async def product_shipping_quote(
    product_id: int,
    country_code: str = Query(..., min_length=2, max_length=2),
    variant_id: int | None = Query(None),
    quantity: int = Query(1, ge=1, le=20),
    zip_code: str = Query("", max_length=64),
    city: str = Query("", max_length=80),
    state: str = Query("", max_length=80),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product or not product.active:
        raise HTTPException(404, "Product not found")
    variant = _resolve_variant(db, product, variant_id)
    try:
        result = await shipping_service.quote([(product, variant, quantity)], country_code,
            {"postcode": zip_code, "city": city, "state": state}, free_us=FREE_SHIPPING)
    except shipping_service.QuoteError as exc:
        return {"available": False, "reason": exc.reason, "message": str(exc),
                "country_code": country_code.upper(), "product_id": product_id,
                "shipping_total": None, "grand_total": None, "options": []}
    return {**result, "product_id": product_id, "variant_id": variant.id if variant else None,
            "quantity": quantity, "options": result["legs"]}


DIGITAL_LOGISTIC = "Digital download"
LULU_LOGISTIC = "Printed to order"


def _printify_line(product: Product, variant: ProductVariant | None, qty: int) -> dict:
    return {"product_id": product.printify_product_id,
            "variant_id": int(variant.printify_variant_id if variant else 0), "quantity": qty}


def _lulu_files(product: Product, variant: ProductVariant | None) -> tuple[str, str] | None:
    """(interior, cover) file names when both are on disk, else None."""
    interior = digital_service.file_for(product, variant)
    cover = (variant.print_cover if variant else "") or ""
    if digital_service.file_path(interior) and digital_service.file_path(cover):
        return interior, cover
    return None


# ── Shipping quote (per country via CJ) ───────────────────────────────


@app.post("/api/shipping/quote")
async def shipping_quote(body: ShippingQuoteIn, db: Session = Depends(get_db)):
    cart = _load_cart_lines(db, body.items)
    try:
        return await shipping_service.quote(cart, body.country_code,
            {"postcode": body.zip_code or "", "city": body.city, "state": body.state,
             "street1": body.street1, "street2": body.street2, "phone_number": body.phone_number,
             "recipient_tax_id": body.recipient_tax_id},
            free_us=FREE_SHIPPING)
    except shipping_service.QuoteError as exc:
        raise HTTPException(exc.status, {"message": str(exc), "reason": exc.reason,
                                       "unavailable_products": exc.products}) from None


# ── Checkout → PayPal ─────────────────────────────────────────────────


class CartPreviewIn(BaseModel):
    items: list[CartItemIn]


@app.post("/api/cart/preview")
def cart_preview(body: CartPreviewIn, lang: str = Query("en"), db: Session = Depends(get_db)):
    """Hydrate cart lines with titles, images, prices for the storefront cart UI."""
    if not body.items:
        return {"items": [], "product_total": 0.0, "count": 0}

    lines_out: list[dict] = []
    product_total = 0.0
    for line in body.items:
        p = db.get(Product, line.product_id)
        if not p or not p.active:
            lines_out.append(
                {
                    "product_id": line.product_id,
                    "variant_id": line.variant_id,
                    "quantity": line.quantity,
                    "available": False,
                    "error": "Product unavailable",
                }
            )
            continue
        try:
            v = _resolve_variant(db, p, line.variant_id)
        except HTTPException:
            lines_out.append(
                {
                    "product_id": line.product_id,
                    "variant_id": line.variant_id,
                    "quantity": line.quantity,
                    "available": False,
                    "error": "Variant unavailable",
                    "title": p.title,
                    "slug": p.slug,
                }
            )
            continue
        unit = float(v.price_usd if v else p.price_usd)
        qty = max(1, min(20, int(line.quantity)))
        line_total = round(unit * qty, 2)
        product_total += line_total
        img = (v.image_url if v and v.image_url else p.image_url) or ""
        name = (v.name if v and v.name else "") or ""
        ptitle = i18n.product_title(p.slug, p.title, lang, p.title_es or "")
        title = ptitle
        if name:
            title = f"{ptitle} — {name}"
        lines_out.append(
            {
                "product_id": p.id,
                "variant_id": v.id if v else None,
                "quantity": qty,
                "available": True,
                "slug": p.slug,
                "title": title,
                "product_title": ptitle,
                "variant_name": name,
                "image_url": img,
                "unit_price": round(unit, 2),
                "line_total": line_total,
                "category": i18n.product(p.to_public(), lang).get("category") or "",
                "digital": digital_service.is_digital(p),
                "supplier": p.supplier or "cj",
                "cj_sku": (v.cj_sku if v else p.cj_sku) or "",
            }
        )

    return {
        "items": lines_out,
        "product_total": round(product_total, 2),
        "count": sum(i["quantity"] for i in lines_out if i.get("available")),
    }


@app.post("/api/checkout")
async def checkout(body: CheckoutIn, db: Session = Depends(get_db)):
    if not paypal_service.configured():
        raise HTTPException(503, "PayPal is not configured yet")

    cart = _load_cart_lines(db, body.items)
    product_total = round(
        sum((v.price_usd if v else p.price_usd) * q for p, v, q in cart), 2
    )
    for p, v, _ in cart:
        # Never take money for a download we cannot hand over.
        if digital_service.is_digital(p) and not digital_service.file_path(digital_service.file_for(p, v)):
            log.error("checkout blocked: no file for digital product %s", p.slug)
            raise HTTPException(503, f"{p.title} is temporarily unavailable. Please try again later.")
        if p.supplier == "prodigi" and not prodigi_store.ready():
            raise HTTPException(503, "This print is temporarily unavailable. Please try again later.")
        if p.supplier == lulu_service.SUPPLIER and not (lulu_service.configured() and _lulu_files(p, v)):
            log.error("checkout blocked: print files or Lulu keys missing for %s", p.slug)
            raise HTTPException(503, f"{p.title} is temporarily unavailable. Please try again later.")
    needs_address = any(not digital_service.is_digital(p) for p, _, _ in cart)
    if needs_address and (
        len(body.shipping_address.strip()) < 3
        or not body.shipping_city.strip()
    ):
        raise HTTPException(422, "Please complete the shipping address.")

    if any(p.supplier == lulu_service.SUPPLIER for p, _, _ in cart):
        if body.shipping_country_code.upper() in {"BR", "CL", "MX"} and not re.fullmatch(r"[A-Za-z0-9.\-/ ]{6,30}", body.recipient_tax_id.strip()):
            raise HTTPException(422, "Please provide the recipient tax ID required for printed books to this country.")
        try:
            lulu_service.address(
                body.customer_name, body.shipping_address, body.shipping_address2 or "",
                body.shipping_city, body.shipping_province, body.shipping_country_code,
                body.shipping_zip or "", body.phone or "",
            )
        except lulu_service.LuluError:
            raise HTTPException(422, "Please provide a valid name, shipping address and phone number for your printed book.") from None

    quote = await shipping_quote(
        ShippingQuoteIn(
            country_code=body.shipping_country_code,
            zip_code=body.shipping_zip or None,
            city=body.shipping_city, state=body.shipping_province,
            street1=body.shipping_address, street2=body.shipping_address2,
            phone_number=body.phone, recipient_tax_id=body.recipient_tax_id, items=body.items,
        ),
        db,
    )
    if quote.get("shipping_total") is None:
        raise HTTPException(503, SHIPPING_UNAVAILABLE_MSG)
    shipping_total = float(quote["shipping_total"])
    if (quote.get("is_estimate") or body.shipping_total is None
            or not math.isfinite(body.shipping_total)
            or abs(body.shipping_total - shipping_total) > 0.005
            or body.expected_total is None or not math.isfinite(body.expected_total)
            or abs(body.expected_total - quote["grand_total"]) > 0.005):
        raise HTTPException(409, "Your delivery total has changed or needs confirmation. Review the updated total before paying.")
    grand_total = round(product_total + shipping_total, 2)
    # Always use the method and price confirmed by the server-side quote.
    logistic_name = quote.get("logistic_name") or "CJPacket"

    order = Order(
        status="awaiting_payment",
        email=body.email,
        customer_name=body.customer_name,
        phone=body.phone or "",
        shipping_address=body.shipping_address,
        shipping_address2=body.shipping_address2 or "",
        shipping_city=body.shipping_city,
        shipping_province=body.shipping_province,
        shipping_zip=body.shipping_zip or "",
        shipping_country=body.shipping_country,
        shipping_country_code=body.shipping_country_code.upper(),
        shipping_tax_id=body.recipient_tax_id.strip(),
        product_total=product_total,
        shipping_total=shipping_total,
        grand_total=grand_total,
        logistic_name=logistic_name,
        shipping_eta=quote.get("eta_days") or "",
    )
    db.add(order)
    db.flush()

    for product, variant, qty in cart:
        unit = variant.price_usd if variant else product.price_usd
        title = product.title
        if variant and variant.name:
            title = f"{product.title} — {variant.name}"
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                variant_id=variant.id if variant else 0,
                title=title,
                quantity=qty,
                unit_price=unit,
                cj_vid=(variant.cj_vid if variant else product.cj_vid) or "",
                cj_sku=(variant.cj_sku if variant else product.cj_sku) or "",
            )
        )
    db.commit()
    db.refresh(order)

    if any(p.supplier == "prodigi" for p, _, _ in cart):
        try:
            prodigi_submission.prepare(db, order, PUBLIC_BASE)
            db.commit()
        except prodigi_store.ProdigiError:
            db.rollback()
            order.status = "failed"
            db.commit()
            raise HTTPException(503, "This print could not be prepared for checkout. Please try again later.") from None

    desc = f"TBW order #{order.id}"
    try:
        checkout_url, paypal_id = await paypal_service.create_checkout(
            order_id=order.id,
            amount_usd=grand_total,
            description=desc,
            return_url=f"{PUBLIC_BASE}/api/checkout/return?order_id={order.id}"
            + ("&lang=es" if body.lang == "es" else ""),
            cancel_url=f"{i18n.url_for('/checkout.html', body.lang)}?status=cancel&order_id={order.id}",
        )
    except paypal_service.PayPalError as exc:
        order.status = "failed"
        order.notes = str(exc)[:500]
        db.commit()
        raise HTTPException(502, f"PayPal error: {exc}") from exc

    order.paypal_order_id = paypal_id
    db.commit()

    return {
        "order_id": order.id,
        "paypal_order_id": paypal_id,
        "checkout_url": checkout_url,
        "grand_total": grand_total,
    }


def _checkout_redirect(status: str, order_id: int, lang: str = "en") -> RedirectResponse:
    # k lets the page show this order's download links, and nobody else's.
    return RedirectResponse(
        f"{i18n.url_for('/checkout.html', lang)}?status={status}&order_id={order_id}"
        f"&k={digital_service.order_key(order_id)}"
    )


@app.get("/api/checkout/return")
async def checkout_return(
    request: Request,
    order_id: int = Query(...),
    token: str | None = Query(None),  # PayPal order id
    lang: str = Query("en"),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    # Only ever capture the PayPal order this shop order created. Trusting the
    # token in the URL let a buyer approve a cheap order and return it under
    # the id of a dear one, which then got marked paid and sent to CJ.
    paypal_id = order.paypal_order_id
    if not paypal_id:
        raise HTTPException(400, "Missing PayPal order")
    if token and token != paypal_id:
        log.warning("checkout return token mismatch for order %s", order.id)
        return _checkout_redirect("payment_error", order.id, lang)

    try:
        status = await _complete_paypal_order(order, db, request=request)
    except Exception as exc:  # provider outages can be retried by PayPal/worker
        db.rollback()
        log.warning("PayPal return order %s: %s", order_id, type(exc).__name__)
        status = "payment_error"
    return _checkout_redirect(status, order.id, lang)


@app.post("/api/webhooks/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    # PayPal events may include buyer information. Neither bodies nor headers
    # belong in logs. Bound the body before JSON parsing or signature work.
    if not paypal_service.PAYPAL_WEBHOOK_ID:
        raise HTTPException(503, "Payment notifications unavailable")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 256 * 1024:
            raise HTTPException(413, "Notification too large")
    try:
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError()
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid notification") from None
    try:
        verified = await paypal_service.verify_webhook(request.headers, event)
    except Exception as exc:
        log.warning("PayPal signature service unavailable: %s", type(exc).__name__)
        raise HTTPException(503, "Payment verification unavailable") from None
    if not verified:
        raise HTTPException(403, "Invalid payment notification signature")

    resource = event.get("resource") or {}
    if not isinstance(resource, dict):
        raise HTTPException(400, "Invalid notification resource")
    kind = event.get("event_type")
    if kind == "CHECKOUT.ORDER.APPROVED":
        paypal_id = resource.get("id")
    elif kind == "PAYMENT.CAPTURE.COMPLETED":
        paypal_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
    else:
        return {"status": "ignored"}
    if not isinstance(paypal_id, str) or not re.fullmatch(r"[A-Za-z0-9]{5,80}", paypal_id):
        return {"status": "ignored"}
    # The merchant app is shared with another store. Only an ID already
    # created and saved by this shop may trigger capture or fulfilment.
    orders = db.query(Order).filter(Order.paypal_order_id == paypal_id).limit(2).all()
    if len(orders) != 1:
        return {"status": "ignored"}
    try:
        result = await _complete_paypal_order(orders[0], db)
    except Exception as exc:
        db.rollback()
        log.warning("PayPal webhook order %s: %s", orders[0].id, type(exc).__name__)
        raise HTTPException(503, "Payment processing unavailable; retry notification") from None
    return {"status": result}


async def _complete_paypal_order(order: Order, db: Session, *, request: Request | None = None) -> str:
    """The one payment/fulfilment path for returns, signed events and recovery.

    Claim paid atomically before any email or supplier POST. Paid orders are
    never auto-resubmitted: an ambiguous supplier result needs reconciliation.
    """
    db.refresh(order)
    if order.status in paypal_recovery.PAID_STATES:
        return "already_paid"
    if order.status != "awaiting_payment":
        return "ignored"
    try:
        await paypal_recovery.confirmed_capture(order)
    except paypal_recovery.NotApproved:
        return "payment_incomplete"
    except paypal_recovery.InvalidPayment as exc:
        log.error("PayPal order %s held: %s", order.id, str(exc))
        return "payment_incomplete"

    # Claim the order atomically so two concurrent returns cannot both send
    # the confirmation email and submit it to CJ twice.
    claimed = (
        db.query(Order)
        .filter(Order.id == order.id, Order.status == "awaiting_payment")
        .update({"status": "paid"}, synchronize_session=False)
    )
    db.commit()
    db.refresh(order)
    if not claimed:
        return "already_paid"

    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    try:
        from services.live_events import record_purchase

        first_slug = None
        if items:
            p0 = db.get(Product, items[0].product_id)
            first_slug = p0.slug if p0 else None
        record_purchase(
            label="paypal",
            uniq_key=order.id,
            value=float(order.grand_total or 0),
            product_slug=first_slug,
            customer_email=order.email,
            extra={
                "order_id": order.id,
                "country": order.shipping_country_code,
                "customer_name": order.customer_name,
            },
        )
    except Exception:  # noqa: BLE001
        pass

    # Meta Conversions API: the browser pixel also fires Purchase here but has no
    # amount, so this is the only event carrying real revenue. Same event_id on
    # both, so Meta counts one conversion. No-ops until META_CAPI_TOKEN is set.
    try:
        from services import geo as geo_service
        from services import meta_capi

        slugs: dict[int, str] = {}
        for it in items:
            prod = db.get(Product, it.product_id)
            if prod and prod.slug:
                slugs[it.product_id] = prod.slug
        await meta_capi.send_purchase(
            order,
            items,
            slugs,
            fbp=request.cookies.get("_fbp") if request else None,
            fbc=request.cookies.get("_fbc") if request else None,
            client_ip=geo_service.extract_client_ip(request) if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )
    except Exception:  # noqa: BLE001
        # A paid order must never fail because of analytics.
        pass

    products_db = {
        p.id: p for p in db.query(Product).filter(Product.id.in_([i.product_id for i in items])).all()
    }
    digital_only = bool(items) and all(digital_service.is_digital(products_db.get(i.product_id)) for i in items)
    if not digital_only:
        try:
            await email_service.send_order_paid(order, items)
        except Exception:  # noqa: BLE001
            # Never block checkout on mail
            pass

    # Push to the suppliers (CJ and/or Printify)
    try:
        await _fulfil(order, db)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        db.refresh(order)
        order.notes = ((order.notes or "") + f"\nPaid; supplier submission needs reconciliation ({type(exc).__name__}). Do not blindly resubmit.")[-2000:]
        order.status = "paid"  # keep paid; manual retry later
        db.commit()
        return "paid_cj_pending"

    return "success"


async def _fulfil(order: Order, db: Session) -> None:
    """Hand a paid order to its suppliers: CJ lines to CJ, print-on-demand
    lines to Printify. Status 'cj_submitted' means every leg was accepted."""
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    if not items:
        raise RuntimeError("Order has no items")
    products_db = {
        p.id: p
        for p in db.query(Product).filter(Product.id.in_([i.product_id for i in items])).all()
    }
    digital = [i for i in items if digital_service.is_digital(products_db.get(i.product_id))]
    pod = [i for i in items if (getattr(products_db.get(i.product_id), "supplier", "") or "cj") == "printify"]
    books = [i for i in items if getattr(products_db.get(i.product_id), "supplier", "") == lulu_service.SUPPLIER]
    art = [i for i in items if getattr(products_db.get(i.product_id), "supplier", "") == "prodigi"]
    unknown = [i for i in items if (getattr(products_db.get(i.product_id), "supplier", "") or "cj") not in {"cj", "digital", "printify", "lulu", "prodigi"}]
    if unknown:
        raise RuntimeError("Unsupported supplier; order held")
    cj_items = [i for i in items if i not in pod and i not in digital and i not in books and i not in art]
    # Downloads first: they need no supplier, so a CJ hiccup never holds
    # back a file the buyer has already paid for.
    if digital:
        await _deliver_digital(order, db, digital, products_db)
    if cj_items:
        await _submit_to_cj(order, db, cj_items, mixed=bool(pod or books or art))
    if pod:
        await _submit_to_printify(order, db, pod, products_db)
    if books:
        await _submit_to_lulu(order, db, books, products_db)

    if art:
        await prodigi_submission.submit(db, order)

    shipped = cj_items or pod or books or art
    order.status = "cj_submitted" if shipped else "delivered"
    db.commit()
    if shipped:
        try:
            await email_service.send_order_fulfillment_started(order, [i for i in items if i not in digital])
        except Exception:  # noqa: BLE001
            pass


def _order_downloads(order_id: int, db: Session) -> list[dict]:
    rows = db.query(DownloadToken).filter(DownloadToken.order_id == order_id).all()
    return [
        {
            "label": r.label,
            "url": digital_service.download_url(PUBLIC_BASE, r.token),
            "expires_at": r.expires_at.isoformat() + "Z",
            "remaining": max(0, r.max_downloads - r.downloads),
        }
        for r in rows
    ]


async def _deliver_digital(order: Order, db: Session, items: list[OrderItem], products_db: dict) -> None:
    """One download link per digital line, then the email that carries them.
    Safe to call twice: lines that already have a token are skipped."""
    have = {
        r.order_item_id
        for r in db.query(DownloadToken).filter(DownloadToken.order_id == order.id).all()
    }
    variants = {
        v.id: v
        for v in db.query(ProductVariant).filter(ProductVariant.id.in_([i.variant_id for i in items])).all()
    }
    created = False
    for it in items:
        if it.id in have:
            continue
        product = products_db[it.product_id]
        name = digital_service.file_for(product, variants.get(it.variant_id))
        if not digital_service.file_path(name):
            raise RuntimeError(f"digital file missing for {product.slug}: {name or '(none set)'}")
        db.add(DownloadToken(
            token=digital_service.new_token(), order_id=order.id, order_item_id=it.id,
            product_id=it.product_id, variant_id=it.variant_id, file_name=name,
            label=it.title, max_downloads=digital_service.max_downloads(),
            expires_at=digital_service.expiry(),
        ))
        created = True
    db.commit()
    if created:
        try:
            await email_service.send_digital_downloads(order, items, _order_downloads(order.id, db))
        except Exception:  # noqa: BLE001
            log.exception("download email failed for order %s", order.id)


async def _submit_to_printify(order: Order, db: Session, items: list[OrderItem], products_db: dict) -> None:
    if order.printify_order_id:  # already accepted on an earlier attempt
        return
    variants = {
        v.id: v
        for v in db.query(ProductVariant).filter(ProductVariant.id.in_([i.variant_id for i in items])).all()
    }
    lines = [
        _printify_line(products_db[i.product_id], variants.get(i.variant_id), i.quantity)
        for i in items
    ]
    first, _, last = (order.customer_name or "").strip().partition(" ")
    address = {
        "first_name": first or order.customer_name,
        "last_name": last or "-",
        "email": order.email,
        "phone": order.phone or "",
        "country": order.shipping_country_code,
        "region": printify_service.region_code(order.shipping_province),
        "address1": order.shipping_address,
        "address2": order.shipping_address2 or "",
        "city": order.shipping_city,
        "zip": order.shipping_zip or "",
    }
    result = await printify_service.create_order(
        external_id=f"tbw-{order.id}", label=f"TBW-{order.id}", lines=lines, address=address
    )
    order.printify_order_id = str(result.get("id") or "")
    db.commit()
    if printify_service.auto_production() and order.printify_order_id:
        await printify_service.send_to_production(order.printify_order_id)


async def _submit_to_lulu(order: Order, db: Session, items: list[OrderItem], products_db: dict) -> None:
    if order.lulu_job_id:  # already accepted on an earlier attempt
        return
    variants = {
        v.id: v
        for v in db.query(ProductVariant).filter(ProductVariant.id.in_([i.variant_id for i in items])).all()
    }
    lines = []
    for it in items:
        product = products_db[it.product_id]
        files = _lulu_files(product, variants.get(it.variant_id))
        if not files:
            raise RuntimeError(f"print files missing for {product.slug}")
        lines.append({
            "external_id": f"tbw-{order.id}-{it.id}",
            "title": it.title,
            "quantity": it.quantity,
            "pod_package_id": product.lulu_package,
            "interior_url": lulu_service.file_url(PUBLIC_BASE, files[0]),
            "cover_url": lulu_service.file_url(PUBLIC_BASE, files[1]),
        })
    address = lulu_service.address(
        order.customer_name, order.shipping_address, order.shipping_address2 or "",
        order.shipping_city, order.shipping_province, order.shipping_country_code,
        order.shipping_zip or "", order.phone or "",
    )
    address["email"] = order.email
    if order.shipping_tax_id:
        address["recipient_tax_id"] = order.shipping_tax_id
    match = re.search(r"\bLulu (MAIL|PRIORITY_MAIL|GROUND_HD|GROUND_BUS|GROUND|EXPEDITED|EXPRESS)\b", order.logistic_name or "")
    if match:
        await lulu_submission.submit(db, order, lines, address, shipping_level=match.group(1))
    else:
        await lulu_submission.submit(db, order, lines, address)


async def _submit_to_cj(order: Order, db: Session, items: list[OrderItem], mixed: bool = False) -> None:
    """Create the CJ order(s). One per warehouse: CJ ships an order from a
    single country, so a cart mixing CN and US stock becomes two CJ orders,
    each on a carrier quoted for its own route. When the order also holds
    Printify lines, the stored carrier name and total cover both suppliers,
    so the CJ leg is requoted and priced on its own lines."""
    products_db = {
        p.id: p
        for p in db.query(Product)
        .filter(Product.id.in_([i.product_id for i in items]))
        .all()
    }
    groups: dict[str, list[OrderItem]] = {}
    for it in items:
        p = products_db.get(it.product_id)
        origin = ((p.from_country if p else "") or "CN").upper()
        groups.setdefault(origin, []).append(it)

    split = len(groups) > 1
    requote = split or mixed
    # Already submitted legs (a retry after a partial failure) are skipped.
    done = dict(
        part.split(":", 1)
        for part in (order.cj_order_id or "").split(",")
        if ":" in part
    )
    for origin, group in groups.items():
        if origin in done:
            continue
        if requote:
            options = await cj_service.freight_calculate(
                start_country=origin,
                end_country=order.shipping_country_code,
                products=[{"vid": it.cj_vid, "quantity": it.quantity} for it in group],
                zip_code=order.shipping_zip or None,
            )
            if not options:
                raise RuntimeError(f"no CJ route {origin} -> {order.shipping_country_code}")
            logistic = str(_pick_freight(options).get("logisticName") or "")
            number = f"TBW-{order.id}-{origin}" if split else f"TBW-{order.id}"
            amount = round(sum(it.unit_price * it.quantity for it in group), 2)
        else:
            logistic = order.logistic_name or "CJPacket Ordinary"
            number = f"TBW-{order.id}"
            amount = order.grand_total

        payload = {
            "orderNumber": number,
            "shippingZip": order.shipping_zip or "00000",
            "shippingCountry": order.shipping_country,
            "shippingCountryCode": order.shipping_country_code,
            "shippingProvince": order.shipping_province,
            "shippingCity": order.shipping_city,
            "shippingPhone": order.phone or "0000000000",
            "shippingCustomerName": order.customer_name,
            "shippingAddress": order.shipping_address,
            "shippingAddress2": order.shipping_address2 or "",
            "email": order.email,
            "remark": f"Web order #{order.id}",
            "payType": CJ_PAY_TYPE,
            "shopAmount": amount,
            "logisticName": logistic,
            "fromCountryCode": origin,
            "platform": "api",
            "orderFlow": 1,
            "products": [
                {
                    "vid": it.cj_vid,
                    "sku": it.cj_sku or None,
                    "quantity": it.quantity,
                    "unitPrice": it.unit_price,
                    "storeLineItemId": f"tbw-{order.id}-{it.id}",
                    "storeProductName": it.title,
                }
                for it in group
            ],
        }
        # Drop null sku fields
        for p in payload["products"]:
            if not p.get("sku"):
                p.pop("sku", None)

        result = await cj_service.create_order(payload)
        cj_id = str(result.get("orderId") or "")
        cj_number = str(result.get("orderNumber") or number)
        if split:
            done[origin] = cj_id
            order.cj_order_id = ",".join(f"{o}:{i}" for o, i in done.items())
            order.cj_order_number = ",".join(
                n for n in [order.cj_order_number, cj_number] if n
            )
        else:
            order.cj_order_id = cj_id
            order.cj_order_number = cj_number
        # Commit per leg so a failure on the second keeps the first on record.
        db.commit()


# ── Admin: add product when you pick one from CJ ──────────────────────


def _unique_slug(db: Session, base: str, exclude_id: int | None = None) -> str:
    slug = base
    n = 2
    while (
        db.query(Product)
        .filter(Product.slug == slug, Product.id != (exclude_id or 0))
        .first()
    ):
        slug = f"{base}-{n}"
        n += 1
    return slug


def _cj_import_plan(
    db: Session,
    details: dict,
    *,
    cj_pid: str,
    cj_vid: str | None = None,
    title: str | None = None,
    slug: str | None = None,
    price_usd: float | None = None,
    description: str | None = None,
    category: str = "",
) -> dict:
    """Store rows for one CJ product with all variants. Writes nothing."""
    cj_variants = details.get("variants") or []
    if not cj_variants:
        raise HTTPException(400, "CJ product has no variants")

    default = _pick_variant(details, cj_vid)
    title = title or details.get("productNameEn") or "Untitled"
    # Prefer short clean title without a specific option name
    slug = _unique_slug(db, slug or _slugify(title))

    from_country = "CN"
    inv = (default.get("inventories") or [{}])[0]
    if inv.get("countryCode"):
        from_country = inv["countryCode"]

    gallery: list[str] = []
    for v in cj_variants:
        if v.get("variantImage") and str(v["variantImage"]) not in gallery:
            gallery.append(str(v["variantImage"]))
    for u in details.get("productImageSet") or []:
        if u and str(u) not in gallery:
            gallery.append(str(u))
    if details.get("bigImage") and str(details["bigImage"]) not in gallery:
        gallery.append(str(details["bigImage"]))

    default_cost = float(default.get("variantSellPrice") or details.get("sellPrice") or 0)
    default_price = (
        price_usd
        if price_usd is not None
        else pricing_service.retail_from_cost(default_cost)
    )
    default_img = (
        default.get("variantImage")
        or details.get("bigImage")
        or (gallery[0] if gallery else "")
        or ""
    )

    product = dict(
        slug=slug,
        title=title,
        # Prefer store-written copy; never paste raw CJ HTML as description
        description=description or "",
        image_url=str(default_img),
        gallery_json=json.dumps(gallery[:16]),
        details_html="",
        category=category or "",
        cj_pid=str(details.get("pid") or cj_pid),
        cj_vid=str(default.get("vid") or ""),
        cj_sku=str(default.get("variantSku") or details.get("productSku") or ""),
        cost_usd=default_cost,
        price_usd=default_price,
        from_country=from_country,
    )

    variants = []
    for i, v in enumerate(cj_variants):
        cost = float(v.get("variantSellPrice") or default_cost or 0)
        price = (
            price_usd
            if price_usd is not None
            else pricing_service.retail_from_cost(cost)
        )
        # Design name: prefer variantKey, else strip base title from variantNameEn
        name = (v.get("variantKey") or "").strip()
        if not name:
            vname = (v.get("variantNameEn") or "").strip()
            base_en = (details.get("productNameEn") or "").strip()
            name = vname.replace(base_en, "").strip(" -") if base_en and vname else vname
        if not name:
            name = f"Option {i + 1}"
        variants.append(
            dict(
                name=name[:200],
                cj_vid=str(v.get("vid") or ""),
                cj_sku=str(v.get("variantSku") or ""),
                image_url=str(v.get("variantImage") or default_img or ""),
                cost_usd=cost,
                price_usd=price,
                sort_order=i,
            )
        )
    return {"product": product, "variants": variants}


def _save_import_plan(db: Session, plan: dict, *, active: bool, draft: bool = False) -> Product:
    product = Product(**plan["product"], active=active, draft=draft)
    db.add(product)
    db.flush()
    for v in plan["variants"]:
        db.add(ProductVariant(product_id=product.id, active=True, **v))
    db.commit()
    db.refresh(product)
    return product


def _draft_key() -> str:
    path = Path(os.getenv("TBW_DRAFT_KEY_FILE", "/etc/thebookswanderer/draft_key"))
    try:
        key = path.read_text().strip()
    except OSError:
        key = ""
    if len(key) < 32:
        raise HTTPException(503, "Draft credential unavailable")
    return key


def _internal_ok(request: Request) -> None:
    """Loopback callers with the draft key only (nginx always adds X-Real-IP)."""
    if request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for"):
        raise HTTPException(404, "Not Found")
    expected = _draft_key()
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), ("Bearer " + expected).encode()):
        raise HTTPException(401, "Unauthorized")


@app.post("/api/admin/products")
async def admin_add_product(body: AddProductIn, db: Session = Depends(get_db)):
    """Import a CJ product as ONE store product with all variants selectable."""
    if not _admin_ok(body.admin_key):
        raise HTTPException(403, "Invalid admin key")

    try:
        details = await cj_service.get_product_details(pid=body.cj_pid)
    except cj_service.CJError as exc:
        raise HTTPException(502, f"CJ product query failed: {exc}") from exc

    plan = _cj_import_plan(
        db, details, cj_pid=body.cj_pid, cj_vid=body.cj_vid, title=body.title,
        slug=body.slug, price_usd=body.price_usd, description=body.description,
        category=body.category,
    )
    product = _save_import_plan(db, plan, active=True)

    # Launch pin (best-effort — never fail the import if Pinterest is down).
    pinterest_launch: dict | None = None
    try:
        from services import pinterest_jobs as pin_jobs

        pinterest_launch = await pin_jobs.pin_product_launch(db, product)
    except Exception as exc:  # noqa: BLE001
        pinterest_launch = {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "product": product.to_detail(),
        "variants": len(product.active_variants()),
        "pinterest_launch": pinterest_launch,
    }


@app.post("/api/internal/drafts")
async def internal_create_draft(
    body: DraftIn, request: Request, preview: bool = Query(False), db: Session = Depends(get_db)
):
    """Hidden, unpinned draft of a CJ product (or its preview) for the admin API."""
    _internal_ok(request)
    existing = db.query(Product).filter(Product.cj_pid == body.cj_pid).first()
    if existing:
        return {
            "ok": True,
            "created": False,
            "existing": {
                "id": existing.id,
                "slug": existing.slug,
                "active": bool(existing.active),
                "draft": bool(existing.draft),
            },
        }
    try:
        details = await cj_service.get_product_details(pid=body.cj_pid)
    except cj_service.CJError as exc:
        log.warning("draft: CJ product query failed for %s: %s", body.cj_pid, exc)
        raise HTTPException(502, "CJ product query failed") from exc
    if not isinstance(details, dict) or not details:
        raise HTTPException(404, "CJ product not found")
    plan = _cj_import_plan(
        db, details, cj_pid=body.cj_pid, cj_vid=body.cj_vid, title=body.title,
        price_usd=body.price_usd, category=body.category,
    )
    if preview:
        return {"ok": True, "created": False, "preview": plan}
    product = _save_import_plan(db, plan, active=False, draft=True)
    return {
        "ok": True,
        "created": True,
        "product": {
            "id": product.id,
            "slug": product.slug,
            "title": product.title,
            "price_usd": product.price_usd,
            "active": False,
            "draft": True,
        },
        "variants": len(plan["variants"]),
    }


def _draft_or_404(db: Session, product_id: int) -> Product:
    """Only hidden drafts: archived or live products are never edited here."""
    product = db.get(Product, product_id)
    if not product or not product.draft or product.active:
        raise HTTPException(404, "Draft not found")
    return product


def _draft_summary(product: Product) -> dict:
    return {
        "id": product.id,
        "slug": product.slug,
        "title": product.title,
        "description": product.description,
        "title_es": product.title_es or "",
        "description_es": product.description_es or "",
        "category": product.category,
        "image_url": product.image_url,
        "price_usd": product.price_usd,
        "cost_usd": product.cost_usd,
        "variants": [
            {"name": v.name, "cost_usd": v.cost_usd, "price_usd": v.price_usd}
            for v in product.active_variants()
        ],
    }


def _publish_problems(product: Product) -> list[str]:
    problems = []
    if len((product.description or "").strip()) < 40:
        problems.append("description is missing or shorter than 40 characters")
    if not cat_service.get_category(product.category):
        slugs = ", ".join(c["slug"] for c in cat_service.all_categories())
        problems.append(f"category must be one of: {slugs}")
    if not product.image_url:
        problems.append("no main image")
    variants = product.active_variants()
    if not variants:
        problems.append("no variants")
    if any(v.price_usd <= v.cost_usd for v in variants):
        problems.append("every variant price must exceed its cost")
    return problems


def _publish_warnings(product: Product) -> list[str]:
    """Not blocking: /es/ falls back to the English copy."""
    if i18n.has_product(product.slug):
        return []
    missing = [n for n, v in (("title_es", product.title_es), ("description_es", product.description_es)) if not v]
    return [f"no Spanish {', '.join(missing)}: /es/ will show the English copy"] if missing else []


def _publish_code(product: Product, action: str = "publish") -> str:
    """Bound to the product's current state: any edit invalidates an earlier code."""
    state = json.dumps([action, _draft_summary(product), bool(product.active)], sort_keys=True)
    digest = hmac.new(_draft_key().encode(), state.encode(), hashlib.sha256)
    return digest.hexdigest()[:6].upper()


@app.post("/api/internal/drafts/{product_id}/update")
async def internal_update_draft(
    product_id: int, body: DraftUpdateIn, request: Request, db: Session = Depends(get_db)
):
    """Edit title, description, category or price of a hidden draft."""
    _internal_ok(request)
    product = _draft_or_404(db, product_id)
    if body.category is not None:
        category = cat_service.get_category(body.category)
        if not category:
            raise HTTPException(422, "Unknown category")
        product.category = category["slug"]
    if body.title is not None:
        product.title = body.title.strip()
        # Never public yet, so the URL can still follow the title.
        product.slug = _unique_slug(db, _slugify(product.title), exclude_id=product.id)
    if body.description is not None:
        product.description = body.description.strip()
    if body.title_es is not None:
        product.title_es = body.title_es.strip()
    if body.description_es is not None:
        product.description_es = body.description_es.strip()
    if body.price_usd is not None:
        product.price_usd = body.price_usd
        for v in product.variants:
            v.price_usd = body.price_usd
    db.commit()
    db.refresh(product)
    return {
        "ok": True,
        "draft": _draft_summary(product),
        "problems": _publish_problems(product),
        "warnings": _publish_warnings(product),
    }


@app.post("/api/internal/drafts/{product_id}/publish")
async def internal_publish_draft(
    product_id: int,
    request: Request,
    body: DraftPublishIn | None = None,
    preview: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Preview returns a code; publishing needs that code for the unchanged draft."""
    _internal_ok(request)
    product = _draft_or_404(db, product_id)
    problems = _publish_problems(product)
    if preview:
        return {
            "ok": True,
            "published": False,
            "draft": _draft_summary(product),
            "url": product_url(product.slug),
            "problems": problems,
            "warnings": _publish_warnings(product),
            "code": None if problems else _publish_code(product),
        }
    if problems:
        raise HTTPException(409, "Draft is not ready: " + "; ".join(problems))
    if body is None or not hmac.compare_digest(body.code.upper(), _publish_code(product)):
        raise HTTPException(409, "Confirmation code does not match the current draft")
    product.active = True
    product.draft = False
    db.commit()
    log.info("draft published: %s", product.slug)
    pinterest_launch: dict | None = None
    if body.pin:
        # Best-effort, as in admin_add_product: never undo a publication.
        try:
            from services import pinterest_jobs as pin_jobs

            pinterest_launch = await pin_jobs.pin_product_launch(db, product)
        except Exception as exc:  # noqa: BLE001
            log.warning("draft launch pin failed for %s: %s", product.slug, exc)
            pinterest_launch = {"ok": False, "error": "pin failed"}
    return {
        "ok": True,
        "published": True,
        "product": {"id": product.id, "slug": product.slug, "url": product_url(product.slug)},
        "pinterest_launch": pinterest_launch,
    }


@app.post("/api/internal/drafts/{product_id}/delete")
async def internal_delete_draft(product_id: int, request: Request, db: Session = Depends(get_db)):
    """Remove a hidden draft that was never sold."""
    _internal_ok(request)
    product = _draft_or_404(db, product_id)
    if db.query(OrderItem).filter(OrderItem.product_id == product.id).first():
        raise HTTPException(409, "Product has orders; keep it hidden instead of deleting it")
    slug = product.slug
    db.delete(product)
    db.commit()
    log.info("draft deleted: %s", slug)
    return {"ok": True, "deleted": True, "slug": slug}


@app.post("/api/internal/products/{product_id}/unpublish")
async def internal_unpublish_product(
    product_id: int,
    request: Request,
    body: ConfirmIn | None = None,
    preview: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Hide a live product and turn it back into an editable draft."""
    _internal_ok(request)
    product = db.get(Product, product_id)
    if not product or not product.active:
        raise HTTPException(404, "Live product not found")
    if preview:
        return {
            "ok": True,
            "unpublished": False,
            "product": _draft_summary(product),
            "url": product_url(product.slug),
            "code": _publish_code(product, "unpublish"),
        }
    if body is None or not hmac.compare_digest(body.code.upper(), _publish_code(product, "unpublish")):
        raise HTTPException(409, "Confirmation code does not match the current product")
    product.active = False
    product.draft = True
    db.commit()
    log.info("product unpublished: %s", product.slug)
    return {"ok": True, "unpublished": True, "product": {"id": product.id, "slug": product.slug}}


# ── Internal: supplier reads for the restricted admin API ─────────────


def _cents(value) -> float | None:
    try:
        return round(float(value) / 100, 2)
    except (TypeError, ValueError):
        return None


def _printify_summary(row: dict, owned: set[str]) -> dict:
    variants = [v for v in row.get("variants") or [] if isinstance(v, dict) and v.get("is_enabled")]
    costs = [c for c in (_cents(v.get("cost")) for v in variants) if c is not None]
    prices = [c for c in (_cents(v.get("price")) for v in variants) if c is not None]
    return {
        "id": str(row.get("id") or ""),
        "title": str(row.get("title") or ""),
        "visible": bool(row.get("visible")),
        "enabled_variants": len(variants),
        "cost_usd_min": min(costs) if costs else None,
        "price_usd_min": min(prices) if prices else None,
        "in_store": str(row.get("id") or "") in owned,
    }


async def _printify_get(path: str):
    try:
        return await printify_service._request("GET", f"/shops/{printify_service.shop_id()}{path}")
    except printify_service.PrintifyError as exc:
        log.warning("internal Printify read failed: %s", exc)
        raise HTTPException(502, "Printify request failed") from None
    except httpx.HTTPError:
        raise HTTPException(502, "Printify unavailable") from None


def _printify_owned(db: Session) -> set[str]:
    rows = db.query(Product.printify_product_id).filter(Product.printify_product_id != "").all()
    return {r[0] for r in rows}


@app.post("/api/internal/suppliers/printify/products")
async def internal_printify_products(
    request: Request, body: PageIn | None = None, db: Session = Depends(get_db)
):
    """Products in the store's Printify shop (read-only)."""
    _internal_ok(request)
    body = body or PageIn()
    data = await _printify_get(f"/products.json?page={body.page}&limit={body.limit}")
    owned = _printify_owned(db)
    rows = data.get("data") if isinstance(data, dict) else None
    return {
        "page": body.page,
        "last_page": data.get("last_page") if isinstance(data, dict) else None,
        "products": [_printify_summary(r, owned) for r in rows or [] if isinstance(r, dict)],
    }


@app.post("/api/internal/suppliers/printify/products/{printify_id}")
async def internal_printify_product(
    printify_id: str, request: Request, db: Session = Depends(get_db)
):
    """One Printify shop product with its enabled variants (read-only)."""
    _internal_ok(request)
    if not re.fullmatch(r"[A-Za-z0-9]{1,64}", printify_id):
        raise HTTPException(422, "Invalid Printify product id")
    row = await _printify_get(f"/products/{printify_id}.json")
    if not isinstance(row, dict) or not row.get("id"):
        raise HTTPException(404, "Printify product not found")
    return {
        **_printify_summary(row, _printify_owned(db)),
        "variants": [
            {"id": v.get("id"), "title": str(v.get("title") or ""),
             "cost_usd": _cents(v.get("cost")), "price_usd": _cents(v.get("price"))}
            for v in row.get("variants") or [] if isinstance(v, dict) and v.get("is_enabled")
        ][:100],
        "images": len(row.get("images") or []),
    }


@app.post("/api/internal/suppliers/prodigi/products/{sku}")
async def internal_prodigi_product(sku: str, request: Request):
    """Prodigi catalogue entry for a SKU (read-only)."""
    _internal_ok(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", sku):
        raise HTTPException(422, "Invalid Prodigi SKU")
    try:
        data = await prodigi_store.request("GET", "/products/" + sku)
    except prodigi_store.ProdigiError:
        raise HTTPException(502, "Prodigi request failed") from None
    product = data.get("product") if isinstance(data.get("product"), dict) else {}
    if not product:
        raise HTTPException(404, "Prodigi product not found")
    variants = [v for v in product.get("variants") or [] if isinstance(v, dict)]
    ships_to = sorted({c for v in variants for c in v.get("shipsTo") or [] if isinstance(c, str)})
    return {
        "sku": str(product.get("sku") or sku),
        "description": str(product.get("description") or ""),
        "dimensions": product.get("productDimensions") or {},
        "attributes": product.get("attributes") or {},
        "print_areas": sorted((product.get("printAreas") or {}).keys()),
        "variants": [
            {"attributes": v.get("attributes") or {}, "ships_to_count": len(v.get("shipsTo") or [])}
            for v in variants
        ][:50],
        "ships_to": ships_to,
    }


@app.post("/api/internal/shipping/{product_id}")
async def internal_shipping_quote(
    product_id: int, body: InternalQuoteIn, request: Request, db: Session = Depends(get_db)
):
    """Customer shipping for a live product or a draft, any supplier (CJ, Printify, Lulu, Prodigi)."""
    _internal_ok(request)
    product = db.get(Product, product_id)
    if not product or not (product.active or product.draft):
        raise HTTPException(404, "Product not found")
    variant = _resolve_variant(db, product, body.variant_id)
    try:
        result = await shipping_service.quote(
            [(product, variant, body.quantity)], body.country_code, free_us=FREE_SHIPPING
        )
    except shipping_service.QuoteError as exc:
        return {"available": False, "reason": exc.reason, "message": str(exc),
                "country_code": body.country_code.upper(), "product_id": product_id}
    return {**result, "available": True, "product_id": product_id,
            "supplier": product.supplier or "cj",
            "variant_id": variant.id if variant else None, "quantity": body.quantity}


@app.post("/api/admin/orders/ship")
async def admin_ship_order(body: ShipOrderIn, db: Session = Depends(get_db)):
    """Mark order as shipped and optionally email tracking to the customer."""
    if not _admin_ok(body.admin_key):
        raise HTTPException(403, "Invalid admin key")
    order = db.get(Order, body.order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    bits = []
    if body.carrier:
        bits.append(body.carrier)
    if body.tracking_number:
        bits.append(body.tracking_number)
    if body.tracking_url:
        bits.append(body.tracking_url)
    note = "Shipped" + (": " + " | ".join(bits) if bits else "")
    prev = (order.notes or "").strip()
    order.notes = (prev + "\n" + note).strip()[:2000] if prev else note[:2000]
    order.status = "shipped"
    db.commit()

    mailed = False
    if body.send_email and order.email:
        try:
            mailed = await email_service.send_order_shipped(
                order,
                items,
                tracking_number=body.tracking_number,
                tracking_url=body.tracking_url,
                carrier=body.carrier,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Order marked shipped but email failed: {exc}") from exc

    return {
        "ok": True,
        "order_id": order.id,
        "status": order.status,
        "email_sent": mailed,
        "email_configured": email_service.configured(),
    }


@app.post("/api/admin/email/cart-reminder")
async def admin_cart_reminder(body: CartReminderIn):
    """Send a 'cart waiting' email (abandoned cart). Cart is browser-only; you pass the payload."""
    if not _admin_ok(body.admin_key):
        raise HTTPException(403, "Invalid admin key")
    if not email_service.configured():
        raise HTTPException(503, "SMTP not configured")
    ok = await email_service.send_cart_reminder(
        email=str(body.email),
        customer_name=body.customer_name,
        lines=body.lines,
    )
    return {"ok": ok, "to": str(body.email)}


@app.post("/api/admin/email/test")
async def admin_email_test(admin_key: str = Query(...), to: EmailStr | None = None):
    """Send a one-line test message to verify SMTP."""
    if not _admin_ok(admin_key):
        raise HTTPException(403, "Invalid admin key")
    if not email_service.configured():
        raise HTTPException(
            503,
            "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, MAIL_FROM in server/.env",
        )
    dest = str(to) if to else (email_service._notify_owner()[0] if email_service._notify_owner() else "")
    if not dest:
        raise HTTPException(400, "No recipient (pass ?to= or set MAIL_NOTIFY_TO)")
    ok = await email_service.send_email(
        to=dest,
        subject=f"Test email — {email_service._shop_name()}",
        text=(
            f"This is a test from The Books Wanderer API.\n\n"
            f"If you received this, SMTP is working.\n"
            f"Shop: {email_service._public_base()}\n"
        ),
        html=None,
    )
    return {"ok": ok, "to": dest, "configured": True}


@app.get("/api/admin/orders")
def admin_list_orders(
    admin_key: str = Query(...),
    db: Session = Depends(get_db),
):
    if not _admin_ok(admin_key):
        raise HTTPException(403, "Invalid admin key")
    rows = db.query(Order).order_by(Order.id.desc()).limit(50).all()
    return {
        "orders": [
            {
                "id": o.id,
                "status": o.status,
                "email": o.email,
                "grand_total": o.grand_total,
                "paypal_order_id": o.paypal_order_id,
                "cj_order_id": o.cj_order_id,
                "country": o.shipping_country_code,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in rows
        ]
    }


def unsubscribe_token(email: str) -> str:
    """Firma el email con SECRET_KEY.

    Sin firma, /api/unsubscribe?email=... permitiria dar de baja a cualquiera
    con solo conocer su direccion. El token es corto porque el enlace va en un
    email y nadie gana nada falsificandolo mas alla de darse de baja a si mismo.
    """
    import hashlib
    import hmac

    secret = (os.getenv("SECRET_KEY", "") or "tbw").encode()
    normalized = (email or "").strip().lower().encode()
    return hmac.new(secret, normalized, hashlib.sha256).hexdigest()[:24]


class NewsletterIn(BaseModel):
    email: EmailStr
    lang: str = "en"
    source: str = "homepage"


async def _send_welcome_step(subscriber_id: int, step: int) -> None:
    """Send one welcome letter and record it. Used right after signup;
    scripts/send_welcome_series.py sends the rest (and retries this one)."""
    from datetime import datetime as _dt

    from database import SessionLocal
    from models import NewsletterSubscriber

    db = SessionLocal()
    try:
        sub = db.get(NewsletterSubscriber, subscriber_id)
        if not sub or not sub.active or (sub.welcome_step or 0) >= step:
            return
        link = f"{PUBLIC_BASE}/api/unsubscribe?email={url_quote(sub.email)}&t={unsubscribe_token(sub.email)}"
        if await email_service.send_welcome(step, sub.email, sub.lang or "en", link, sub.source or ""):
            sub.welcome_step = step
            sub.welcome_at = _dt.utcnow()
            db.commit()
    except Exception:  # noqa: BLE001
        log.exception("welcome email %s failed for subscriber %s", step, subscriber_id)
    finally:
        db.close()


@app.post("/api/newsletter/subscribe")
def newsletter_subscribe(body: NewsletterIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Guarda la dirección de verdad.

    Antes el formulario de la portada solo respondía "You're in! Check your
    inbox" desde JavaScript y descartaba el email: no había lista, ni backend,
    ni confirmación que revisar.
    """
    from models import EmailOptOut, NewsletterSubscriber

    normalized = body.email.strip().lower()

    # Quien pidió no recibir correos no vuelve a entrar por aquí.
    if db.query(EmailOptOut).filter(EmailOptOut.email == normalized).one_or_none():
        return {"ok": True, "already": True}

    existing = (
        db.query(NewsletterSubscriber)
        .filter(NewsletterSubscriber.email == normalized)
        .one_or_none()
    )
    lang = "es" if body.lang == "es" else "en"
    if existing:
        existing.active = True
        db.commit()
        if not existing.welcome_step:
            background.add_task(_send_welcome_step, existing.id, 1)
        return {"ok": True, "already": True}

    source = re.sub(r"[^a-z0-9-]", "", (body.source or "homepage").lower())[:40] or "homepage"
    sub = NewsletterSubscriber(email=normalized, lang=lang, source=source)
    db.add(sub)
    db.commit()
    # The free Reading Challenge goes out straight away.
    background.add_task(_send_welcome_step, sub.id, 1)
    return {"ok": True, "already": False}


@app.get("/api/unsubscribe", response_class=HTMLResponse)
def unsubscribe(
    email: str = Query(...),
    t: str = Query(...),
    db: Session = Depends(get_db),
):
    """Baja de los recordatorios de carrito. Un clic, sin login."""
    import hmac as _hmac
    from html import escape as _esc_html

    from models import EmailOptOut

    normalized = email.strip().lower()
    if not _hmac.compare_digest(t, unsubscribe_token(normalized)):
        raise HTTPException(400, "Invalid unsubscribe link")

    from models import NewsletterSubscriber

    existing = (
        db.query(EmailOptOut).filter(EmailOptOut.email == normalized).one_or_none()
    )
    if not existing:
        db.add(EmailOptOut(email=normalized))
    # La baja vale para todo, no solo para los recordatorios de carrito.
    db.query(NewsletterSubscriber).filter(
        NewsletterSubscriber.email == normalized
    ).update({"active": False})
    db.commit()

    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Unsubscribed · The Books Wanderer</title>
<link rel="stylesheet" href="/styles.css?v=23"></head>
<body class="page-product"><main class="legal"><div class="container legal__inner">
<h1>You're unsubscribed</h1>
<p>We won't send <strong>{_esc_html(normalized)}</strong> any more cart reminders.</p>
<p>Order confirmations and shipping updates still go out when you buy something —
those aren't marketing, and you'd want them.</p>
<p><a href="/">Back to the shop</a></p>
</div></main></body></html>"""
    )


@app.get("/api/checkout/status/{order_id}")
def checkout_status(order_id: int, k: str | None = Query(None), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    out = {
        "order_id": order.id,
        "status": order.status,
        "grand_total": order.grand_total,
        "cj_order_id": order.cj_order_id or None,
    }
    if digital_service.check_order_key(order.id, k):
        out["downloads"] = _order_downloads(order.id, db)
    return out


@app.api_route("/api/print-files/{name}", methods=["GET", "HEAD"])
def print_file(name: str, sig: str | None = Query(None)):
    """Interior and cover PDFs for Lulu to fetch; the link is signed."""
    path = digital_service.file_path(name)
    if not path or not lulu_service.check_file_sig(name, sig):
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@app.api_route("/api/download/{token}", methods=["GET", "HEAD"])
def download_file(token: str, request: Request, db: Session = Depends(get_db)):
    """Serve a purchased file. The token is the only credential."""
    from fastapi.responses import FileResponse

    row = db.query(DownloadToken).filter(DownloadToken.token == token).first()
    if not row:
        raise HTTPException(404, "This download link is not valid.")
    if datetime.utcnow() > row.expires_at:
        raise HTTPException(410, "This download link has expired. Write to hello@thebookswanderer.com for a new one.")
    if row.downloads >= row.max_downloads:
        raise HTTPException(410, "This link has reached its download limit. Write to hello@thebookswanderer.com for a new one.")
    path = digital_service.file_path(row.file_name)
    if not path:
        log.error("digital file missing on disk: %s (token %s)", row.file_name, row.id)
        raise HTTPException(503, "The file is temporarily unavailable. We have been notified.")
    if request.method == "GET":
        row.downloads += 1
        db.commit()
    return FileResponse(
        path,
        filename=path.name,
        headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"},
    )


# Simple HTML ping (optional)
@app.get("/api/", response_class=HTMLResponse)
def api_root():
    return "<p>The Books Wanderer API. See <a href='/api/health'>/api/health</a></p>"


@app.api_route("/api/prodigi/artwork/{name}", methods=["GET", "HEAD"])
def prodigi_artwork(name: str, sig: str = Query("")):
    if not prodigi_store.check_asset_signature(name, sig):
        raise HTTPException(404, "File not found")
    try:
        path = prodigi_store.asset_path()
    except prodigi_store.ProdigiError:
        raise HTTPException(404, "File not found") from None
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
