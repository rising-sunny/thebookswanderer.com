"""
The Books Wanderer — store API
Static site + FastAPI (CJ Dropshipping + PayPal), same VPS pattern as mathrelaxing.store.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).resolve().parent / ".env")

from database import get_db, init_db  # noqa: E402
from models import Order, OrderItem, Product, ProductVariant  # noqa: E402
from services import cj as cj_service  # noqa: E402
from services import paypal as paypal_service  # noqa: E402
from services import pricing as pricing_service  # noqa: E402

PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "https://thebookswanderer.com").rstrip("/")
SHIP_MARKUP = float(os.getenv("SHIPPING_MARKUP", "1.15"))
CJ_PAY_TYPE = int(os.getenv("CJ_PAY_TYPE", "3"))

app = FastAPI(title="The Books Wanderer API", version="0.1.0")

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
        "pricing": pricing_service.pricing_config(),
    }


@app.get("/api/pricing/preview")
def pricing_preview(cost_usd: float = Query(..., ge=0)):
    """Debug helper: cost → retail breakdown (no auth; no secrets)."""
    return pricing_service.breakdown(cost_usd).as_dict()


@app.get("/api/products")
def list_products(db: Session = Depends(get_db)):
    rows = (
        db.query(Product)
        .filter(Product.active.is_(True))
        .order_by(Product.id.desc())
        .all()
    )
    return {"products": [p.to_public() for p in rows], "count": len(rows)}


@app.get("/api/products/by-slug/{slug}")
async def get_product_by_slug(slug: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.slug == slug, Product.active.is_(True)).first()
    if not p:
        raise HTTPException(404, "Product not found")
    await _ensure_product_media(p, db)
    return p.to_detail()


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
            cancel_url=f"{PUBLIC_BASE}/?checkout=cancel",
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


@app.get("/api/checkout/return")
async def checkout_return(
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
        return RedirectResponse(f"{PUBLIC_BASE}/?checkout=already_paid&order_id={order.id}")

    try:
        capture = await paypal_service.capture_order(paypal_id)
    except paypal_service.PayPalError as exc:
        order.notes = f"capture failed: {exc}"[:500]
        db.commit()
        return RedirectResponse(f"{PUBLIC_BASE}/?checkout=payment_error&order_id={order.id}")

    status = (capture.get("status") or "").upper()
    if status not in ("COMPLETED", "APPROVED"):
        # capture payload may nest status
        pu = (capture.get("purchase_units") or [{}])[0]
        captures = ((pu.get("payments") or {}).get("captures") or [{}])
        cap_status = (captures[0].get("status") if captures else "") or ""
        if cap_status.upper() != "COMPLETED" and status != "COMPLETED":
            order.notes = f"PayPal status={status}"
            db.commit()
            return RedirectResponse(
                f"{PUBLIC_BASE}/?checkout=payment_incomplete&order_id={order.id}"
            )

    order.status = "paid"
    order.paypal_order_id = paypal_id
    db.commit()

    # Push to CJ Dropshipping
    try:
        await _submit_to_cj(order, db)
    except Exception as exc:  # noqa: BLE001
        order.notes = f"paid but CJ submit failed: {exc}"[:800]
        order.status = "paid"  # keep paid; manual retry later
        db.commit()
        return RedirectResponse(
            f"{PUBLIC_BASE}/?checkout=paid_cj_pending&order_id={order.id}"
        )

    return RedirectResponse(f"{PUBLIC_BASE}/?checkout=success&order_id={order.id}")


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
