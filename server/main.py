"""
The Books Wanderer — store API
Static site + FastAPI (CJ Dropshipping + PayPal), same VPS pattern as mathrelaxing.store.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).resolve().parent / ".env")

from database import get_db, init_db  # noqa: E402
from models import Order, OrderItem, Product, ProductVariant  # noqa: E402
from services import categories as cat_service  # noqa: E402
from services import cj as cj_service  # noqa: E402
from services import email as email_service  # noqa: E402
from services import paypal as paypal_service  # noqa: E402
from services import pricing as pricing_service  # noqa: E402
from ssr import (  # noqa: E402
    affiliate_by_slug,
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
from routers.pinterest import router as pinterest_router  # noqa: E402
SHIP_MARKUP = float(os.getenv("SHIPPING_MARKUP", "1.15"))
CJ_PAY_TYPE = int(os.getenv("CJ_PAY_TYPE", "3"))

app = FastAPI(title="The Books Wanderer API", version="0.1.0")
app.include_router(live_router)
app.include_router(pinterest_router)

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


# ── Schemas ──────────────────────────────────────────────────────────


class CartItemIn(BaseModel):
    product_id: int
    variant_id: int | None = None  # required when product has variants
    quantity: int = Field(ge=1, le=20)


class ShippingQuoteIn(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    zip_code: str | None = None
    items: list[CartItemIn]


class CheckoutIn(BaseModel):
    email: EmailStr
    customer_name: str = Field(min_length=2, max_length=80)
    phone: str = ""
    shipping_address: str = Field(min_length=3, max_length=200)
    shipping_address2: str = ""
    shipping_city: str = Field(min_length=1, max_length=80)
    shipping_province: str = Field(min_length=1, max_length=80)
    shipping_zip: str = ""
    shipping_country: str = Field(min_length=2, max_length=80)
    shipping_country_code: str = Field(min_length=2, max_length=2)
    items: list[CartItemIn]
    logistic_name: str = ""
    shipping_total: float | None = None  # client can pass quote; revalidated server-side


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
        "products": [p.to_public() for p in rows],
        "count": len(rows),
        "category": filter_slug,
    }


@app.get("/api/products/by-slug/{slug}")
async def get_product_by_slug(slug: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.slug == slug, Product.active.is_(True)).first()
    if not p:
        raise HTTPException(404, "Product not found")
    await _ensure_product_media(p, db)
    return p.to_detail()


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


@app.get("/products/{slug}", response_class=HTMLResponse)
async def product_page_pretty(slug: str, db: Session = Depends(get_db)):
    """Canonical product PDP (SSR)."""
    p = db.query(Product).filter(Product.slug == slug, Product.active.is_(True)).first()
    if not p:
        return HTMLResponse(render_product_not_found(slug), status_code=404)
    await _ensure_product_media(p, db)
    detail = p.to_detail()
    canonical = product_url(p.slug)
    return HTMLResponse(render_product_page(detail, canonical=canonical))


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


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/index.html", methods=["GET", "HEAD"], response_class=HTMLResponse)
def home_page_ssr(db: Session = Depends(get_db)):
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
    products = [p.to_public() for p in rows]
    counts: dict[str, int] = {c["slug"]: 0 for c in cat_service.all_categories()}
    for p in rows:
        counts[cat_service.normalize_category(p.category)] = (
            counts.get(cat_service.normalize_category(p.category), 0) + 1
        )
    categories = []
    for c in cat_service.all_categories():
        categories.append({**c, "product_count": counts.get(c["slug"], 0)})
    aff = load_affiliate_catalog()
    html_out = inject_home_seo(
        raw, products=products, affiliate=aff, categories=categories
    )
    return HTMLResponse(html_out)


@app.get("/collections", response_class=HTMLResponse)
def collections_index(db: Session = Depends(get_db)):
    """Index of all storefront collections."""
    rows = db.query(Product).filter(Product.active.is_(True)).all()
    counts: dict[str, int] = {c["slug"]: 0 for c in cat_service.all_categories()}
    for p in rows:
        s = cat_service.normalize_category(p.category)
        counts[s] = counts.get(s, 0) + 1
    categories = [{**c, "product_count": counts.get(c["slug"], 0)} for c in cat_service.all_categories()]
    canonical = f"{PUBLIC_BASE}/collections"
    return HTMLResponse(render_collections_index(categories, canonical=canonical))


@app.get("/collections/{slug}", response_class=HTMLResponse)
def collection_page(slug: str, db: Session = Depends(get_db)):
    """Category landing page with SSR product grid + JSON-LD."""
    cat = cat_service.get_category(slug)
    if not cat:
        return HTMLResponse(render_collection_not_found(slug), status_code=404)
    rows = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.id.desc())
        .all()
    )
    products = [
        p.to_public()
        for p in rows
        if cat_service.normalize_category(p.category) == cat["slug"]
    ]
    all_cats = cat_service.all_categories()
    canonical = collection_url(cat["slug"])
    return HTMLResponse(
        render_collection_page(
            cat, products, canonical=canonical, all_cats=all_cats
        )
    )


@app.get("/sitemap.xml")
def sitemap_xml(db: Session = Depends(get_db)):
    """Dynamic sitemap from live catalog (products + picks + collections)."""
    site_root = Path(__file__).resolve().parent.parent
    today = datetime.now(timezone.utc).date().isoformat()
    urls: list[tuple[str, str, str, str]] = []  # loc, lastmod, changefreq, priority

    urls.append((f"{PUBLIC_BASE}/", today, "weekly", "1.0"))
    urls.append((f"{PUBLIC_BASE}/collections", today, "weekly", "0.85"))

    for c in cat_service.all_categories():
        urls.append((collection_url(c["slug"]), today, "weekly", "0.85"))

    for rel, prio in (
        ("about.html", "0.6"),
        ("contact.html", "0.5"),
        ("shipping-returns.html", "0.5"),
        ("privacy.html", "0.3"),
    ):
        path = site_root / rel
        if path.is_file():
            urls.append(
                (
                    f"{PUBLIC_BASE}/{rel}",
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

    rows = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.slug.asc())
        .all()
    )
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
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod, freq, prio in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
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
async def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p or not p.active:
        raise HTTPException(404, "Product not found")
    await _ensure_product_media(p, db)
    return p.to_detail()


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

# Markets we actively quote. A country only "works" for a product if CJ
# returns at least one freight option for that variant.
SHIP_DESTINATIONS: list[dict[str, str]] = [
    {"code": "US", "name": "United States"},
    {"code": "CA", "name": "Canada"},
    {"code": "GB", "name": "United Kingdom"},
    {"code": "AU", "name": "Australia"},
    {"code": "NZ", "name": "New Zealand"},
    {"code": "DE", "name": "Germany"},
    {"code": "FR", "name": "France"},
    {"code": "ES", "name": "Spain"},
    {"code": "IT", "name": "Italy"},
    {"code": "NL", "name": "Netherlands"},
    {"code": "BE", "name": "Belgium"},
    {"code": "PT", "name": "Portugal"},
    {"code": "IE", "name": "Ireland"},
    {"code": "AT", "name": "Austria"},
    {"code": "CH", "name": "Switzerland"},
    {"code": "SE", "name": "Sweden"},
    {"code": "NO", "name": "Norway"},
    {"code": "DK", "name": "Denmark"},
    {"code": "FI", "name": "Finland"},
    {"code": "PL", "name": "Poland"},
    {"code": "CL", "name": "Chile"},
    {"code": "MX", "name": "Mexico"},
    {"code": "BR", "name": "Brazil"},
    {"code": "AR", "name": "Argentina"},
    {"code": "CO", "name": "Colombia"},
    {"code": "PE", "name": "Peru"},
    {"code": "JP", "name": "Japan"},
    {"code": "KR", "name": "South Korea"},
    {"code": "SG", "name": "Singapore"},
    {"code": "AE", "name": "United Arab Emirates"},
]


@app.get("/api/shipping/destinations")
def shipping_destinations():
    return {"destinations": SHIP_DESTINATIONS}


@app.get("/api/products/{product_id}/shipping")
async def product_shipping_quote(
    product_id: int,
    country_code: str = Query(..., min_length=2, max_length=2),
    variant_id: int | None = Query(None),
    quantity: int = Query(1, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Quote shipping for one product line to a country (CJ freight + markup).
    Returns available=false when CJ has no route for this variant/destination.
    """
    product = db.get(Product, product_id)
    if not product or not product.active:
        raise HTTPException(404, "Product not found")

    variant = _resolve_variant(db, product, variant_id)
    vid = (variant.cj_vid if variant else product.cj_vid) or ""
    if not vid:
        raise HTTPException(400, "Product has no CJ variant id")

    unit_price = float(variant.price_usd if variant else product.price_usd)
    product_total = round(unit_price * quantity, 2)
    origin = (product.from_country or "CN").upper()
    country = country_code.upper()

    try:
        options = await cj_service.freight_calculate(
            start_country=origin,
            end_country=country,
            products=[{"vid": vid, "quantity": quantity}],
        )
    except cj_service.CJError as exc:
        return {
            "available": False,
            "country_code": country,
            "product_id": product_id,
            "variant_id": variant.id if variant else None,
            "quantity": quantity,
            "product_total": product_total,
            "shipping_total": None,
            "grand_total": None,
            "message": str(exc) or "Could not quote shipping",
            "options": [],
        }

    if not options:
        return {
            "available": False,
            "country_code": country,
            "product_id": product_id,
            "variant_id": variant.id if variant else None,
            "quantity": quantity,
            "product_total": product_total,
            "shipping_total": None,
            "grand_total": None,
            "message": "Shipping is not available to this country for this item",
            "options": [],
        }

    ranked = sorted(options, key=lambda o: float(o.get("logisticPrice") or 0))
    best = ranked[0]
    ship_cost = float(best.get("logisticPrice") or 0)
    ship_retail = round(ship_cost * SHIP_MARKUP, 2)

    return {
        "available": True,
        "country_code": country,
        "from_country": origin,
        "product_id": product_id,
        "variant_id": variant.id if variant else None,
        "quantity": quantity,
        "product_total": product_total,
        "shipping_total": ship_retail,
        "shipping_cost_raw": round(ship_cost, 2),
        "grand_total": round(product_total + ship_retail, 2),
        "eta_days": best.get("logisticAging"),
        "logistic_name": best.get("logisticName"),
        "options": [
            {
                "name": o.get("logisticName"),
                "eta_days": o.get("logisticAging"),
                "cost_usd": round(float(o.get("logisticPrice") or 0), 2),
                "retail_usd": round(
                    float(o.get("logisticPrice") or 0) * SHIP_MARKUP, 2
                ),
            }
            for o in ranked[:6]
        ],
    }


# ── Shipping quote (per country via CJ) ───────────────────────────────


@app.post("/api/shipping/quote")
async def shipping_quote(body: ShippingQuoteIn, db: Session = Depends(get_db)):
    cart = _load_cart_lines(db, body.items)
    country = body.country_code.upper()
    by_origin: dict[str, list[dict]] = {}
    for product, variant, qty in cart:
        origin = (product.from_country or "CN").upper()
        vid = (variant.cj_vid if variant else product.cj_vid) or ""
        if not vid:
            raise HTTPException(400, f"Product {product.id} has no CJ variant id")
        by_origin.setdefault(origin, []).append({"vid": vid, "quantity": qty})

    options_all: list[dict] = []
    retail_shipping = 0.0
    eta_bits: list[str] = []
    chosen_names: list[str] = []

    for origin, products in by_origin.items():
        try:
            options = await cj_service.freight_calculate(
                start_country=origin,
                end_country=country,
                products=products,
                zip_code=body.zip_code,
            )
        except cj_service.CJError as exc:
            raise HTTPException(502, f"CJ freight error: {exc}") from exc

        if not options:
            raise HTTPException(
                400,
                f"No shipping options from {origin} to {country} for this cart",
            )

        best = min(options, key=lambda o: float(o.get("logisticPrice") or 0))
        cost = float(best.get("logisticPrice") or 0)
        retail_shipping += cost * SHIP_MARKUP
        eta_bits.append(str(best.get("logisticAging") or ""))
        chosen_names.append(str(best.get("logisticName") or ""))

        options_all.append(
            {
                "from": origin,
                "options": [
                    {
                        "name": o.get("logisticName"),
                        "eta_days": o.get("logisticAging"),
                        "cost_usd": round(float(o.get("logisticPrice") or 0), 2),
                        "retail_usd": round(
                            float(o.get("logisticPrice") or 0) * SHIP_MARKUP, 2
                        ),
                    }
                    for o in sorted(
                        options, key=lambda x: float(x.get("logisticPrice") or 0)
                    )[:8]
                ],
            }
        )

    product_total = sum(
        (v.price_usd if v else p.price_usd) * q for p, v, q in cart
    )
    shipping_total = round(retail_shipping, 2)

    return {
        "country_code": country,
        "product_total": round(product_total, 2),
        "shipping_total": shipping_total,
        "grand_total": round(product_total + shipping_total, 2),
        "eta_days": " / ".join(e for e in eta_bits if e) or None,
        "logistic_name": " + ".join(chosen_names),
        "legs": options_all,
    }


# ── Checkout → PayPal ─────────────────────────────────────────────────


class CartPreviewIn(BaseModel):
    items: list[CartItemIn]


@app.post("/api/cart/preview")
def cart_preview(body: CartPreviewIn, db: Session = Depends(get_db)):
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
        title = p.title
        if name:
            title = f"{p.title} — {name}"
        lines_out.append(
            {
                "product_id": p.id,
                "variant_id": v.id if v else None,
                "quantity": qty,
                "available": True,
                "slug": p.slug,
                "title": title,
                "product_title": p.title,
                "variant_name": name,
                "image_url": img,
                "unit_price": round(unit, 2),
                "line_total": line_total,
                "category": p.to_public().get("category") or "",
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

    quote = await shipping_quote(
        ShippingQuoteIn(
            country_code=body.shipping_country_code,
            zip_code=body.shipping_zip or None,
            items=body.items,
        ),
        db,
    )
    shipping_total = float(quote["shipping_total"])
    grand_total = round(product_total + shipping_total, 2)
    logistic_name = body.logistic_name or quote.get("logistic_name") or "CJPacket"

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

    desc = f"TBW order #{order.id}"
    try:
        checkout_url, paypal_id = await paypal_service.create_checkout(
            order_id=order.id,
            amount_usd=grand_total,
            description=desc,
            return_url=f"{PUBLIC_BASE}/api/checkout/return?order_id={order.id}",
            cancel_url=f"{PUBLIC_BASE}/checkout.html?status=cancel&order_id={order.id}",
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


def _checkout_redirect(status: str, order_id: int) -> RedirectResponse:
    return RedirectResponse(
        f"{PUBLIC_BASE}/checkout.html?status={status}&order_id={order_id}"
    )


@app.get("/api/checkout/return")
async def checkout_return(
    request: Request,
    order_id: int = Query(...),
    token: str | None = Query(None),  # PayPal order id
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    paypal_id = token or order.paypal_order_id
    if not paypal_id:
        raise HTTPException(400, "Missing PayPal token")

    if order.status in ("paid", "cj_submitted", "fulfilled"):
        return _checkout_redirect("already_paid", order.id)

    try:
        capture = await paypal_service.capture_order(paypal_id)
    except paypal_service.PayPalError as exc:
        order.notes = f"capture failed: {exc}"[:500]
        db.commit()
        return _checkout_redirect("payment_error", order.id)

    status = (capture.get("status") or "").upper()
    if status not in ("COMPLETED", "APPROVED"):
        # capture payload may nest status
        pu = (capture.get("purchase_units") or [{}])[0]
        captures = ((pu.get("payments") or {}).get("captures") or [{}])
        cap_status = (captures[0].get("status") if captures else "") or ""
        if cap_status.upper() != "COMPLETED" and status != "COMPLETED":
            order.notes = f"PayPal status={status}"
            db.commit()
            return _checkout_redirect("payment_incomplete", order.id)

    order.status = "paid"
    order.paypal_order_id = paypal_id
    db.commit()

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
            fbp=request.cookies.get("_fbp"),
            fbc=request.cookies.get("_fbc"),
            client_ip=geo_service.extract_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except Exception:  # noqa: BLE001
        # A paid order must never fail because of analytics.
        pass

    try:
        await email_service.send_order_paid(order, items)
    except Exception:  # noqa: BLE001
        # Never block checkout on mail
        pass

    # Push to CJ Dropshipping
    try:
        await _submit_to_cj(order, db)
    except Exception as exc:  # noqa: BLE001
        order.notes = f"paid but CJ submit failed: {exc}"[:800]
        order.status = "paid"  # keep paid; manual retry later
        db.commit()
        return _checkout_redirect("paid_cj_pending", order.id)

    return _checkout_redirect("success", order.id)


async def _submit_to_cj(order: Order, db: Session) -> None:
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    if not items:
        raise RuntimeError("Order has no items")

    # fromCountry: use first product's warehouse
    products_db = {
        p.id: p
        for p in db.query(Product)
        .filter(Product.id.in_([i.product_id for i in items]))
        .all()
    }
    from_country = "CN"
    for it in items:
        p = products_db.get(it.product_id)
        if p and p.from_country:
            from_country = p.from_country
            break

    payload = {
        "orderNumber": f"TBW-{order.id}",
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
        "shopAmount": order.grand_total,
        "logisticName": order.logistic_name or "CJPacket Ordinary",
        "fromCountryCode": from_country,
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
            for it in items
        ],
    }
    # Drop null sku fields
    for p in payload["products"]:
        if not p.get("sku"):
            p.pop("sku", None)

    result = await cj_service.create_order(payload)
    order.cj_order_id = str(result.get("orderId") or "")
    order.cj_order_number = str(result.get("orderNumber") or payload["orderNumber"])
    order.status = "cj_submitted"
    db.commit()

    try:
        await email_service.send_order_fulfillment_started(order, items)
    except Exception:  # noqa: BLE001
        pass


# ── Admin: add product when you pick one from CJ ──────────────────────


@app.post("/api/admin/products")
async def admin_add_product(body: AddProductIn, db: Session = Depends(get_db)):
    """Import a CJ product as ONE store product with all variants selectable."""
    if not _admin_ok(body.admin_key):
        raise HTTPException(403, "Invalid admin key")

    try:
        details = await cj_service.get_product_details(pid=body.cj_pid)
    except cj_service.CJError as exc:
        raise HTTPException(502, f"CJ product query failed: {exc}") from exc

    import json as _json
    import re as _re

    cj_variants = details.get("variants") or []
    if not cj_variants:
        raise HTTPException(400, "CJ product has no variants")

    default = _pick_variant(details, body.cj_vid)
    title = body.title or details.get("productNameEn") or "Untitled"
    # Prefer short clean title without a specific option name
    slug = body.slug or _slugify(title)
    base = slug
    n = 2
    while db.query(Product).filter(Product.slug == slug).first():
        slug = f"{base}-{n}"
        n += 1

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
        body.price_usd
        if body.price_usd is not None
        else pricing_service.retail_from_cost(default_cost)
    )
    default_img = (
        default.get("variantImage")
        or details.get("bigImage")
        or (gallery[0] if gallery else "")
        or ""
    )

    product = Product(
        slug=slug,
        title=title,
        # Prefer store-written copy; never paste raw CJ HTML as description
        description=body.description or "",
        image_url=str(default_img),
        gallery_json=_json.dumps(gallery[:16]),
        details_html="",
        category=body.category or "",
        cj_pid=str(details.get("pid") or body.cj_pid),
        cj_vid=str(default.get("vid") or ""),
        cj_sku=str(default.get("variantSku") or details.get("productSku") or ""),
        cost_usd=default_cost,
        price_usd=default_price,
        from_country=from_country,
        active=True,
    )
    db.add(product)
    db.flush()

    for i, v in enumerate(cj_variants):
        cost = float(v.get("variantSellPrice") or default_cost or 0)
        price = (
            body.price_usd
            if body.price_usd is not None
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
        db.add(
            ProductVariant(
                product_id=product.id,
                name=name[:200],
                cj_vid=str(v.get("vid") or ""),
                cj_sku=str(v.get("variantSku") or ""),
                image_url=str(v.get("variantImage") or default_img or ""),
                cost_usd=cost,
                price_usd=price,
                sort_order=i,
                active=True,
            )
        )

    db.commit()
    db.refresh(product)
    return {
        "ok": True,
        "product": product.to_detail(),
        "variants": len(product.active_variants()),
    }


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


@app.post("/api/newsletter/subscribe")
def newsletter_subscribe(body: NewsletterIn, db: Session = Depends(get_db)):
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
    if existing:
        existing.active = True
        db.commit()
        return {"ok": True, "already": True}

    db.add(NewsletterSubscriber(email=normalized))
    db.commit()
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
def checkout_status(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return {
        "order_id": order.id,
        "status": order.status,
        "grand_total": order.grand_total,
        "cj_order_id": order.cj_order_id or None,
    }


# Simple HTML ping (optional)
@app.get("/api/", response_class=HTMLResponse)
def api_root():
    return "<p>The Books Wanderer API. See <a href='/api/health'>/api/health</a></p>"
