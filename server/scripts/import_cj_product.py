"""
Import a CJ SPU as ONE store product with all variants + lifestyle gallery.
Usage (on VPS or local with CJ_API_KEY + DB):
  .venv/bin/python scripts/import_cj_product.py CJJT1393855 --title "..." --price 12.99 --slug "..."
  .venv/bin/python scripts/import_cj_product.py CJJT1393855 --spec
      # title, slug, category and description from scripts/cj_products.json
      # (the run-script workflow splits arguments on spaces, so long text goes there)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def cj_token(api_key: str) -> str:
    req = urllib.request.Request(
        "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken",
        data=json.dumps({"apiKey": api_key}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        body = json.loads(r.read().decode())
    tok = (body.get("data") or {}).get("accessToken")
    if not tok:
        raise SystemExit(f"auth failed: {body}")
    return tok


def _round99(value: float) -> float:
    import math

    return math.floor(value) + 0.99


def _ship_allowance(vid: str, *, from_country: str = "CN") -> float:
    """Worst freight across the advertised markets, grossed up for PayPal.

    Same basis as scripts/reprice_all_in.py. Returns 0 when shipping is still
    charged at checkout, or when CJ cannot quote the variant.
    """
    free = (os.getenv("FREE_SHIPPING", "1") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not free or not vid:
        return 0.0

    import asyncio

    from services import cj

    markup = float(os.getenv("SHIPPING_MARKUP", "1.15"))
    paypal_pct = float(os.getenv("PAYPAL_FEE_PCT", "0.0349"))

    async def worst() -> float:
        found = 0.0
        for country in ("US", "GB", "AU"):
            try:
                options = await cj.freight_calculate(
                    start_country=from_country,
                    end_country=country,
                    products=[{"vid": vid, "quantity": 1}],
                )
            except Exception:  # noqa: BLE001
                options = []
            await asyncio.sleep(1.3)  # CJ allows one request per second
            if options:
                found = max(
                    found, min(float(o.get("logisticPrice") or 0) for o in options)
                )
        return found

    try:
        freight = asyncio.run(worst())
    except Exception:  # noqa: BLE001
        return 0.0
    return (freight * markup) / (1 - paypal_pct) if freight else 0.0


def cj_query(token: str, sku: str) -> dict:
    url = f"https://developers.cjdropshipping.com/api2.0/v1/product/query?productSku={sku}"
    req = urllib.request.Request(url, headers={"CJ-Access-Token": token})
    with urllib.request.urlopen(req, timeout=45) as r:
        body = json.loads(r.read().decode())
    if body.get("code") != 200:
        raise SystemExit(f"query failed: {body}")
    return body.get("data") or {}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (s or "product")[:100]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sku", help="CJ SPU / productSku")
    ap.add_argument("--title", default="")
    ap.add_argument("--description", default="")
    ap.add_argument("--category", default="Collection")
    ap.add_argument("--price", type=float, default=None)
    ap.add_argument("--slug", default="")
    ap.add_argument("--spec", action="store_true", help="Take title/slug/category/description from cj_products.json")
    args = ap.parse_args()
    if args.spec:
        specs = json.loads((Path(__file__).with_name("cj_products.json")).read_text(encoding="utf-8"))
        if args.sku not in specs:
            raise SystemExit(f"{args.sku} is not in cj_products.json")
        for key, value in specs[args.sku].items():
            if not getattr(args, key, None) or key == "category":
                setattr(args, key, value)

    api_key = os.getenv("CJ_API_KEY", "")
    if not api_key:
        raise SystemExit("CJ_API_KEY required")

    from database import SessionLocal, init_db
    from models import Product, ProductVariant

    init_db()
    token = cj_token(api_key)
    details = cj_query(token, args.sku)
    print("pid", details.get("pid"))
    print("name", details.get("productNameEn"))
    print("sellPrice", details.get("sellPrice"))
    cj_variants = details.get("variants") or []
    print("variants", len(cj_variants))
    for v in cj_variants:
        print(" -", v.get("variantKey") or v.get("variantNameEn"), v.get("vid"), v.get("variantSellPrice"))

    # Save raw for reference
    out = ROOT / "data" / f"{args.sku}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8")
    print("saved", out)

    title = args.title or details.get("productNameEn") or args.sku
    # Prefer shorter title if too long
    if not args.title and len(title) > 70:
        title = title[:67].rsplit(" ", 1)[0] + "…"

    default_desc = args.description
    slug = args.slug or slugify(title if args.title else details.get("productSku") or title)

    variant_imgs = set()
    for v in cj_variants:
        if v.get("variantImage"):
            variant_imgs.add(str(v["variantImage"]))

    lifestyle: list[str] = []
    for u in details.get("productImageSet") or []:
        if u and str(u) not in variant_imgs and str(u) not in lifestyle:
            lifestyle.append(str(u))
    if details.get("bigImage") and str(details["bigImage"]) not in variant_imgs:
        if str(details["bigImage"]) not in lifestyle:
            lifestyle.insert(0, str(details["bigImage"]))
    for m in re.finditer(r'src="(https://[^"]+)"', details.get("description") or ""):
        u = m.group(1)
        if u not in variant_imgs and u not in lifestyle:
            lifestyle.append(u)
    lifestyle = lifestyle[:14]

    default = cj_variants[0]
    from services import pricing as pricing_service

    default_cost = float(default.get("variantSellPrice") or details.get("sellPrice") or 0)
    # Shipping is priced into the product, so the allowance has to land before
    # the launch pin fires — a pin created at the pre-allowance price cannot be
    # edited afterwards (Pinterest gates PATCH behind the pin_edit feature).
    ship_allowance = _ship_allowance(default.get("vid") or "", from_country="CN")
    default_price = (
        args.price
        if args.price is not None
        else _round99(
            pricing_service.retail_from_cost(default_cost) + ship_allowance
        )
    )
    if ship_allowance:
        print(f"shipping allowance ${ship_allowance:.2f} folded into the price")
    default_img = (
        default.get("variantImage")
        or details.get("bigImage")
        or (lifestyle[0] if lifestyle else "")
        or ""
    )

    from_country = "CN"
    inv = (default.get("inventories") or [{}])[0]
    if inv.get("countryCode"):
        from_country = inv["countryCode"]

    db = SessionLocal()
    # If slug exists, update; else create
    product = db.query(Product).filter(Product.slug == slug).first()
    if not product:
        # also match by cj_pid
        product = (
            db.query(Product)
            .filter(Product.cj_pid == str(details.get("pid") or ""), Product.active.is_(True))
            .first()
        )
    if not product:
        product = Product(slug=slug)
        db.add(product)
    else:
        # free slug if reusing pid product with different slug
        product.slug = slug

    product.title = title
    product.description = default_desc
    product.image_url = str(default_img)
    product.gallery_json = json.dumps(lifestyle)
    product.details_html = ""
    product.category = args.category
    product.cj_pid = str(details.get("pid") or "")
    product.cj_vid = str(default.get("vid") or "")
    product.cj_sku = str(default.get("variantSku") or details.get("productSku") or "")
    product.cost_usd = default_cost
    product.price_usd = default_price
    product.from_country = from_country
    product.active = True
    db.flush()

    for v in list(product.variants or []):
        db.delete(v)
    db.flush()

    for i, v in enumerate(cj_variants):
        cost = float(v.get("variantSellPrice") or default_cost or 0)
        # Checkout charges each variant's own price, so the shipping allowance
        # has to be in it too, not only in the product's headline price.
        price = (
            args.price
            if args.price is not None
            else _round99(pricing_service.retail_from_cost(cost) + ship_allowance)
        )
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
    print("OK product", product.id, product.slug, "variants", len(product.active_variants()))
    print("lifestyle", len(lifestyle), "price", default_price)

    # Launch pin (optional; skip with PINTEREST_LAUNCH_PIN_ENABLED=0)
    try:
        import asyncio

        from services import pinterest_jobs as pin_jobs

        launch = asyncio.run(pin_jobs.pin_product_launch(db, product))
        print("pinterest_launch", json.dumps(launch, default=str))
    except Exception as exc:  # noqa: BLE001
        print("pinterest_launch failed:", exc)

    db.close()


if __name__ == "__main__":
    main()
