"""Server-rendered HTML for SEO (Googlebot / Search Console).

Static product.html was a JS shell ("Loading product…") → Soft 404 in GSC.
These helpers emit unique title, description, substantial body text, and JSON-LD.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SITE_ROOT = ROOT.parent
PUBLIC_BASE = "https://thebookswanderer.com"


def _esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _esc_text(s: Any) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def _css_ver() -> str:
    p = SITE_ROOT / "styles.css"
    try:
        return str(int(p.stat().st_mtime))
    except OSError:
        return "20"


def _meta_description(text: str, *, limit: int = 155) -> str:
    """Plain SERP/OG description: no smart quotes, hard cap ~155 chars."""
    s = str(text or "")
    # Normalize curly quotes / fancy dashes from copy
    for a, b in (
        ("\u2019", "'"),
        ("\u2018", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2014", "-"),
        ("\u2013", "-"),
        ("…", "..."),
        ("\xa0", " "),
    ):
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= limit:
        return s
    cut = s[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return (cut or s[: limit - 1]) + "..."


DEFAULT_OG_IMAGE = f"{PUBLIC_BASE}/assets/og-default.jpg"
DEFAULT_OG_W = 1200
DEFAULT_OG_H = 630


def _social_head(
    *,
    title: str,
    description: str,
    canonical: str,
    image: str = "",
    og_type: str = "website",
    site_name: str = "The Books Wanderer",
    image_alt: str = "",
) -> str:
    """Shared Open Graph + Twitter tags (aligned with title/description)."""
    img = image or DEFAULT_OG_IMAGE
    if img.startswith("/"):
        img = PUBLIC_BASE + img
    is_default = img.rstrip("/").endswith("og-default.jpg")
    alt = image_alt or title
    lines = [
        f'<meta property="og:type" content="{_esc(og_type)}">',
        f'<meta property="og:site_name" content="{_esc(site_name)}">',
        f'<meta property="og:title" content="{_esc(title)}">',
        f'<meta property="og:description" content="{_esc(description)}">',
        f'<meta property="og:url" content="{_esc(canonical)}">',
        f'<meta property="og:image" content="{_esc(img)}">',
        f'<meta property="og:image:alt" content="{_esc(alt)}">',
        f'<meta property="og:locale" content="en_US">',
        f'<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{_esc(title)}">',
        f'<meta name="twitter:description" content="{_esc(description)}">',
        f'<meta name="twitter:image" content="{_esc(img)}">',
        f'<meta name="twitter:image:alt" content="{_esc(alt)}">',
    ]
    if is_default:
        lines.insert(
            6,
            f'<meta property="og:image:width" content="{DEFAULT_OG_W}">',
        )
        lines.insert(
            7,
            f'<meta property="og:image:height" content="{DEFAULT_OG_H}">',
        )
        lines.insert(
            8,
            '<meta property="og:image:type" content="image/jpeg">',
        )
    return "\n    ".join(lines)


def _ship_countries() -> list[str]:
    """Códigos de país a los que enviamos, para la política de devoluciones.

    Importación diferida: main.py importa ssr.py, así que hacerlo arriba sería
    un ciclo. En tiempo de petición main ya está cargado. La lista tiene una
    sola fuente de verdad y no se duplica aquí.
    """
    try:
        from main import SHIP_DESTINATIONS

        return [d["code"] for d in SHIP_DESTINATIONS]
    except Exception:  # noqa: BLE001
        return ["GB", "US"]


# Transit bands from shipping-returns.html (carrier working-day guide).
# shippingRate uses maxValue (Google allows value OR maxValue) because the
# live quote is destination + variant via CJ — a single flat value would lie.
_SHIP_TRANSIT_BANDS: list[dict[str, Any]] = [
    {
        "codes": ["GB", "ES", "IT", "FR", "PT", "PL", "IE", "JP", "NZ", "AT", "DK", "FI"],
        "transit_min": 4,
        "transit_max": 11,
        "rate_max_usd": 18.0,
    },
    {
        "codes": ["US", "SG", "CH", "NO", "SE", "AU"],
        "transit_min": 5,
        "transit_max": 11,
        "rate_max_usd": 18.0,
    },
    {
        "codes": ["CA", "DE", "NL", "BE"],
        "transit_min": 7,
        "transit_max": 15,
        "rate_max_usd": 22.0,
    },
    # MY sits here, not with SG, despite being closer to the CN origin: the quote
    # picks the cheapest carrier and for MY that is a 15-30 day line, while SG
    # gets 5-10 days for a similar price.
    {
        "codes": ["CL", "MX", "BR", "AR", "CO", "PE", "KR", "AE", "MY"],
        "transit_min": 12,
        "transit_max": 60,
        "rate_max_usd": 35.0,
    },
]


def _merchant_return_policy() -> dict[str, Any]:
    """JSON-LD MerchantReturnPolicy aligned with shipping-returns.html.

    Change-of-mind: 14 days from delivery. For most of the catalogue we do not
    ask the customer to post the item back (KeepProduct + FreeReturn). Damaged
    goods: 30-day replace/refund without return — FreeReturn still fits.
    """
    return {
        "@type": "MerchantReturnPolicy",
        "applicableCountry": _ship_countries(),
        "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
        "merchantReturnDays": 14,
        "returnMethod": "https://schema.org/KeepProduct",
        "returnFees": "https://schema.org/FreeReturn",
        "merchantReturnLink": f"{PUBLIC_BASE}/shipping-returns.html",
    }


def _free_shipping() -> bool:
    """Mirrors main.FREE_SHIPPING. Deferred import: main imports ssr."""
    try:
        from main import FREE_SHIPPING

        return bool(FREE_SHIPPING)
    except Exception:  # noqa: BLE001
        return False


def _shipping_rate(band: dict[str, Any]) -> dict[str, Any]:
    """What Google is told shipping costs.

    With shipping priced into the product this must be a flat 0, not a
    ceiling — a merchant listing that advertises a rate we never charge is
    worse than no rate at all.
    """
    if _free_shipping():
        return {"@type": "MonetaryAmount", "value": 0, "currency": "USD"}
    return {
        "@type": "MonetaryAmount",
        # Ceiling, not a quote — exact amount is calculated at PDP/cart.
        "maxValue": float(band["rate_max_usd"]),
        "currency": "USD",
    }


def _shipping_details() -> list[dict[str, Any]]:
    """OfferShippingDetails per transit band for countries we actually ship to."""
    allowed = set(_ship_countries())
    details: list[dict[str, Any]] = []
    covered: set[str] = set()
    for band in _SHIP_TRANSIT_BANDS:
        codes = [c for c in band["codes"] if c in allowed]
        if not codes:
            continue
        covered.update(codes)
        details.append(
            {
                "@type": "OfferShippingDetails",
                "shippingDestination": {
                    "@type": "DefinedRegion",
                    "addressCountry": codes,
                },
                "shippingRate": _shipping_rate(band),
                "deliveryTime": {
                    "@type": "ShippingDeliveryTime",
                    "handlingTime": {
                        "@type": "QuantitativeValue",
                        "minValue": 1,
                        "maxValue": 3,
                        "unitCode": "DAY",
                    },
                    "transitTime": {
                        "@type": "QuantitativeValue",
                        "minValue": int(band["transit_min"]),
                        "maxValue": int(band["transit_max"]),
                        "unitCode": "DAY",
                    },
                },
            }
        )
    # Any SHIP_DESTINATIONS code not in a band still needs a row (wide window).
    leftover = sorted(allowed - covered)
    if leftover:
        details.append(
            {
                "@type": "OfferShippingDetails",
                "shippingDestination": {
                    "@type": "DefinedRegion",
                    "addressCountry": leftover,
                },
                "shippingRate": _shipping_rate({"rate_max_usd": 35.0}),
                "deliveryTime": {
                    "@type": "ShippingDeliveryTime",
                    "handlingTime": {
                        "@type": "QuantitativeValue",
                        "minValue": 1,
                        "maxValue": 3,
                        "unitCode": "DAY",
                    },
                    "transitTime": {
                        "@type": "QuantitativeValue",
                        "minValue": 7,
                        "maxValue": 60,
                        "unitCode": "DAY",
                    },
                },
            }
        )
    return details


def _related_block_html(related: list[dict[str, Any]]) -> str:
    """"You may also like" row. Empty string when there is nothing to show."""
    if not related:
        return ""
    cards = "".join(_product_card_html(p) for p in related)
    return f"""
<section class="section" aria-labelledby="relatedTitle" style="padding-top:var(--sp-7)">
    <div class="container">
        <div class="section__head">
            <div>
                <p class="eyebrow">More for readers</p>
                <h2 id="relatedTitle">You may also like</h2>
            </div>
            <a class="link-more" href="/collections">
                All collections
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14m-6-7 7 7-7 7"/></svg>
            </a>
        </div>
        <div class="products">{cards}</div>
    </div>
</section>"""


def render_product_page(
    detail: dict[str, Any],
    *,
    canonical: str,
    related: list[dict[str, Any]] | None = None,
) -> str:
    """Full HTML document for a store product (CJ catalog)."""
    title = detail.get("title") or "Product"
    page_title = f"{title} | The Books Wanderer"
    desc = (detail.get("description") or "").strip()
    if not desc:
        desc = (
            f"{title} from The Books Wanderer - a curated reading accessory "
            f"for book lovers. Ships worldwide with secure PayPal checkout."
        )
    meta_desc = _meta_description(desc)

    price = detail.get("price_usd")
    price_max = detail.get("price_max_usd", price)
    img = detail.get("image_url") or ""
    if img.startswith("/"):
        img = PUBLIC_BASE + img
    category = detail.get("category") or "Shop"
    cat_slug = detail.get("category_slug") or ""
    slug = detail.get("slug") or ""
    product_id = detail.get("id")
    related_html = _related_block_html(related or [])
    variants = detail.get("variants") or []
    lifestyle = detail.get("lifestyle_images") or detail.get("images") or []

    tiene_rango = (
        price is not None
        and price_max is not None
        and float(price_max) > float(price)
    )
    if tiene_rango:
        price_block = f"${float(price):.2f}–${float(price_max):.2f} USD"
    elif price is not None:
        price_block = f"${float(price):.2f} USD"
    else:
        price_block = ""

    # Microdatos del precio.
    #
    # Antes el importe visible iba dentro de itemprop="price", asi que Google
    # leia "$9.99 USD" -- o peor, "$9.99-$27.99 USD" -- donde espera un numero
    # pelado. De ahi el "formato de precio no valido" de Search Console. El dato
    # legible por maquina va ahora en <meta content>, y el texto para personas
    # queda fuera del itemprop, que es como se marca esto.
    if price is None:
        price_microdata = ""
    else:
        tipo = "AggregateOffer" if tiene_rango else "Offer"
        if tiene_rango:
            importes = (
                f'<meta itemprop="lowPrice" content="{float(price):.2f}">'
                f'<meta itemprop="highPrice" content="{float(price_max):.2f}">'
            )
        else:
            importes = f'<meta itemprop="price" content="{float(price):.2f}">'
        price_microdata = (
            '<p class="pdp__price">'
            f'<strong itemprop="offers" itemscope itemtype="https://schema.org/{tipo}">'
            '<meta itemprop="priceCurrency" content="USD">'
            f"{importes}"
            '<meta itemprop="availability" content="https://schema.org/InStock">'
            f"{_esc_text(price_block)}"
            "</strong></p>"
        )

    # JSON-LD Product + BreadcrumbList (helps avoid thin-page / soft-404 signals)
    json_ld_product: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "description": desc,
        "sku": str(detail.get("cj_sku") or slug),
        "url": canonical,
        "brand": {"@type": "Brand", "name": "The Books Wanderer"},
        "category": category,
    }
    if img:
        json_ld_product["image"] = [img]
    if price is not None:
        # Con variantes a distintos precios, un solo "price" contradice al rango
        # que se ve en pantalla. AggregateOffer es lo que describe eso.
        if tiene_rango:
            importe: dict[str, Any] = {
                "@type": "AggregateOffer",
                "lowPrice": f"{float(price):.2f}",
                "highPrice": f"{float(price_max):.2f}",
                "offerCount": max(len(variants), 1),
            }
        else:
            importe = {"@type": "Offer", "price": f"{float(price):.2f}"}
        json_ld_product["offers"] = {
            **importe,
            "url": canonical,
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": "The Books Wanderer"},
            # Merchant listings (GSC): return policy + shipping bands.
            # Policy text source of truth: shipping-returns.html.
            "hasMerchantReturnPolicy": _merchant_return_policy(),
            "shippingDetails": _shipping_details(),
        }
    # mpn helps the "identifier / brand" merchant signal (no GTIN from CJ).
    mpn = str(detail.get("cj_sku") or detail.get("sku") or "").strip()
    if mpn:
        json_ld_product["mpn"] = mpn

    json_ld_breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": PUBLIC_BASE + "/",
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Shop",
                "item": PUBLIC_BASE + "/products/",
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": title,
                "item": canonical,
            },
        ],
    }

    ld_product = json.dumps(json_ld_product, ensure_ascii=False)
    ld_crumbs = json.dumps(json_ld_breadcrumb, ensure_ascii=False)
    v = _css_ver()

    variant_lis = ""
    if variants:
        items = []
        for var in variants[:24]:
            name = var.get("name") or "Option"
            vp = var.get("price_usd")
            price_bit = f" — ${float(vp):.2f} USD" if vp is not None else ""
            items.append(f"<li>{_esc_text(name)}{price_bit}</li>")
        variant_lis = (
            "<section class=\"pdp-ssr__section\">"
            f"<h2>Available options ({len(variants)})</h2>"
            f"<ul>{''.join(items)}</ul>"
            "</section>"
        )

    life_bits = ""
    if lifestyle:
        imgs = []
        for i, src in enumerate(lifestyle[:6]):
            s = src if not str(src).startswith("/") else PUBLIC_BASE + str(src)
            imgs.append(
                f'<img {_cj_img_attrs(s, widths=(400, 600), sizes=SIZES_THUMB)} alt="{_esc(title)} lifestyle photo {i + 1}" '
                f'width="400" height="400" loading="lazy" '
                f'style="max-width:48%;height:auto;margin:0.25rem;border-radius:8px">'
            )
        life_bits = (
            '<section class="pdp-ssr__section">'
            "<h2>Product gallery</h2>"
            f"<div>{''.join(imgs)}</div>"
            "</section>"
        )

    # itemprop="image" es lo que faltaba: la etiqueta estaba, pero sin declarar
    # que era la imagen del producto. El <article> de microdatos es un item
    # aparte del JSON-LD y Google los valida por separado, asi que tener la
    # imagen solo en el JSON-LD no salvaba a este.
    hero = (
        f'<img itemprop="image" {_cj_img_attrs(img, base_w=900, sizes=SIZES_PDP_HERO)} alt="{_esc(title)}" width="800" height="1000" '
        f'style="max-width:min(100%,420px);height:auto;border-radius:12px;display:block;margin:1rem 0">'
        if img
        # Sin foto de producto, el logo mantiene el item valido.
        else f'<meta itemprop="image" content="{PUBLIC_BASE}/assets/logo.png">'
    )

    # Substantial article body — Google Soft 404 is often thin / empty pages.
    ssr_body = f"""
<article class="pdp-ssr" data-ssr="1" itemscope itemtype="https://schema.org/Product">
  <p class="eyebrow">{_esc_text(category)}</p>
  <h1 itemprop="name">{_esc_text(title)}</h1>
  {price_microdata}
  {hero}
  <div itemprop="description">
    <p>{_esc_text(desc)}</p>
  </div>
  <section class="pdp-ssr__section">
    <h2>About this piece</h2>
    <p>
      {_esc_text(title)} is part of The Books Wanderer literary boutique —
      accessories chosen for everyday reading, not novelty clutter.
      We list real stock options, clear USD pricing, and ship with tracking.
      Checkout is secured with PayPal.
    </p>
    <ul>
      <li>Category: {_esc_text(category)}</li>
      <li>Ships from partner warehouses (typically China origin unless noted)</li>
      <li>Faulty or wrong items refunded in full within 30 days</li>
      <li>Secure checkout · shipping calculated by destination at cart</li>
    </ul>
  </section>
  {variant_lis}
  {life_bits}
  <section class="pdp-ssr__section">
    <h2>Buy {_esc_text(title)}</h2>
    <p>
      Select your preferred option on this page, add it to your cart, and complete
      checkout when you are ready. Questions about fit or materials are welcome
      before you order.
    </p>
    <p><a href="{_esc(canonical)}">Open product page</a> ·
       <a href="/products/">Browse the full catalog</a> ·
       <a href="/cart.html">View cart</a></p>
  </section>
</article>
""".strip()

    social = _social_head(
        title=page_title,
        description=meta_desc,
        canonical=canonical,
        image=img,
        og_type="product",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(page_title)}</title>
    <meta name="description" content="{_esc(meta_desc)}">
    <meta name="robots" content="index,follow,max-image-preview:large">
    <link rel="canonical" href="{_esc(canonical)}">
    {social}
    <meta name="theme-color" content="#f8f2e5">
    <link rel="icon" href="/assets/favicon.ico" sizes="any">
    <link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
    <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png" sizes="180x180">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;1,500&family=Karla:wght@400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/styles.css?v={_esc(v)}">
    <script type="application/ld+json">{ld_product}</script>
    <script type="application/ld+json">{ld_crumbs}</script>
</head>
<body class="page-product">
<a class="skip-link" href="#main">Skip to content</a>
<header class="header is-stuck" id="header">
    <div class="container header__inner">
        <a class="brand" href="/" aria-label="The Books Wanderer, home">
            <span class="brand__emblem" aria-hidden="true"></span>
            <span class="brand__name">
                The Books Wanderer
                <span class="brand__tagline">Literary boutique</span>
            </span>
        </a>
        <nav class="nav" id="nav" aria-label="Primary" style="display:none"></nav>
        <div class="actions">
            <a class="icon-btn" href="/products/" aria-label="Back to shop">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M19 12H5m6-7-7 7 7 7"/></svg>
            </a>
            <a class="icon-btn" href="/cart.html" id="cartBtn" data-cart-btn aria-label="Shopping cart">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 7h12l-1 12H7L6 7Z"/><path d="M9 7a3 3 0 0 1 6 0"/></svg>
                <span class="cart-count" id="cartCount" data-count="0" aria-hidden="true">0</span>
            </a>
        </div>
    </div>
</header>
<main id="main" class="pdp">
    <div class="container">
        <nav class="pdp__crumb" aria-label="Breadcrumb">
            <a href="/">Home</a> · <a href="/products/">Shop</a>
            {f' · <a href="/collections/{_esc(cat_slug)}">{_esc_text(category)}</a>' if cat_slug else ""}
            · <span id="pdpCrumb">{_esc_text(title)}</span>
        </nav>
        <div id="pdpRoot" class="pdp__layout" data-product-id="{_esc(product_id or "")}" data-slug="{_esc(slug)}">
            {ssr_body}
        </div>
    </div>
    {related_html}
</main>
<footer class="footer" style="margin-top:var(--sp-8)">
    <div class="container">
        <nav class="footer__links" aria-label="Footer">
            <a href="/about.html">About</a>
            <a href="/guides/hold-a-book-open-one-handed/">Holding a book open</a>
            <a href="/shipping-returns.html">Shipping &amp; returns</a>
            <a href="/contact.html">Contact</a>
            <a href="/privacy.html">Privacy &amp; cookies</a>
        </nav>
        <div class="footer__bottom" style="border:0;padding-top:var(--sp-5)">
        <p class="footer__quote">“For those who wander between pages.”</p>
        <p class="footer__affiliate">As an Amazon Associate I earn from qualifying purchases.</p>
        <p class="footer__legal">&copy; 2026 The Books Wanderer · {_esc_text(title)}</p>
    </div>
    </div>
</footer>
<script src="/track.js?v=4" defer></script>
<script src="/cart.js?v=3" defer></script>
<script src="/product.js?v=25" defer></script>
</body>
</html>
"""


def render_product_not_found(slug: str = "") -> str:
    msg = f'We could not find “{_esc_text(slug)}”.' if slug else "Product not found."
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Product not found | The Books Wanderer</title>
  <meta name="robots" content="noindex,follow">
  <meta name="description" content="This product is not available in The Books Wanderer catalog.">
  <link rel="stylesheet" href="/styles.css?v={_esc(_css_ver())}">
</head>
<body class="page-product">
  <main class="container" style="padding:3rem 1rem">
    <h1>Product not found</h1>
    <p>{msg}</p>
    <p>Browse our <a href="/products/">reader catalog</a> for available pieces.</p>
  </main>
</body>
</html>
"""


def load_affiliate_catalog() -> dict[str, Any]:
    """Shared Amazon picks JSON (site root)."""
    for path in (
        SITE_ROOT / "affiliate-products.json",
        ROOT / "data" / "affiliate_products.json",
    ):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
    return {
        "siteDisclosure": "As an Amazon Associate I earn from qualifying purchases.",
        "linkDisclosure": "As an Amazon Associate we earn from qualifying purchases.",
        "paidLinkLabel": "paid link",
        "products": [],
    }


def affiliate_by_slug(slug: str) -> dict[str, Any] | None:
    data = load_affiliate_catalog()
    key = (slug or "").strip().lower()
    for p in data.get("products") or []:
        if str(p.get("slug", "")).lower() == key:
            return p
    return None


def render_pick_page(pick: dict[str, Any], *, canonical: str) -> str:
    """SSR for Amazon affiliate pick pages (avoid Soft 404)."""
    cat = load_affiliate_catalog()
    title = pick.get("title") or pick.get("shortTitle") or "Reader pick"
    page_title = f"{title} | The Books Wanderer"
    short = pick.get("shortTitle") or title
    blurb = (pick.get("blurb") or "").strip()
    desc = (pick.get("description") or blurb or title).strip()
    # Prefer blurb for SERP (shorter, marketing-friendly); fall back to full description
    meta_desc = _meta_description(blurb or desc)

    img = pick.get("imageUrl") or ""
    images = list(pick.get("images") or [])
    if img and img not in images:
        images.insert(0, img)
    if not images and img:
        images = [img]

    bullets = pick.get("bullets") or []
    bullet_html = "".join(f"<li>{_esc_text(b)}</li>" for b in bullets)
    gallery = "".join(
        f'<img {_cj_img_attrs(u, widths=(400, 600), sizes=SIZES_THUMB)} alt="{_esc(title)} photo {i + 1}" width="400" height="400" '
        f'loading="lazy" style="max-width:46%;height:auto;margin:0.25rem;border-radius:8px;background:#fff">'
        for i, u in enumerate(images[:8])
    )
    hero = images[0] if images else ""
    amazon = pick.get("amazonUrl") or "#"
    badge = pick.get("badge") or ""
    merchant = pick.get("merchant") or "Amazon"
    category = pick.get("category") or "E-readers"
    disclosure = cat.get("siteDisclosure") or "As an Amazon Associate I earn from qualifying purchases."
    paid = cat.get("paidLinkLabel") or "paid link"

    pairs_html = ""
    for x in pick.get("pairsWith") or []:
        href = x.get("href") or (
            f"/products/{_esc(x.get('slug'))}" if x.get("slug") else "#"
        )
        # href already needs raw path; escape attr only
        label = x.get("label") or x.get("slug") or "Related"
        pairs_html += (
            f'<a class="pick-pair" href="{_esc(href)}">{_esc_text(label)}</a> '
        )

    # No usar @type Product en picks de Amazon.
    #
    # Estas paginas recomiendan un producto que vende Amazon, no nosotros: el
    # precio cambia a diario y Associates no permite inventarlo. Un Product sin
    # offers (o con Offer incompleto) lo reporta Search Console como product
    # snippet invalido ("falta price en offers"). WebPage describe la pagina
    # sin reclamar rich results de producto.
    primary_img = (images[0] if images else None) or img or f"{PUBLIC_BASE}/assets/logo.png"
    json_ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": page_title,
        "description": meta_desc,
        "url": canonical,
        "isPartOf": {
            "@type": "WebSite",
            "name": "The Books Wanderer",
            "url": f"{PUBLIC_BASE}/",
        },
        "primaryImageOfPage": {
            "@type": "ImageObject",
            "url": primary_img,
        },
        "about": {
            "@type": "Thing",
            "name": title,
            "description": desc,
        },
    }
    asin = (pick.get("asin") or "").strip()
    if asin:
        json_ld["about"]["identifier"] = asin

    ld = json.dumps(json_ld, ensure_ascii=False)
    v = _css_ver()
    embed = json.dumps(cat, ensure_ascii=False)
    social = _social_head(
        title=page_title,
        description=meta_desc,
        canonical=canonical,
        image=hero or img,
        og_type="website",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(page_title)}</title>
    <meta name="description" content="{_esc(meta_desc)}">
    <meta name="robots" content="index,follow,max-image-preview:large">
    <link rel="canonical" href="{_esc(canonical)}">
    {social}
    <meta name="theme-color" content="#f8f2e5">
    <link rel="icon" href="/assets/favicon.ico" sizes="any">
    <link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
    <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png" sizes="180x180">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;1,500&family=Karla:wght@400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/styles.css?v={_esc(v)}">
    <script type="application/ld+json">{ld}</script>
    <script type="application/json" id="affiliate-products-json">{embed}</script>
</head>
<body class="page-product page-pick">
<a class="skip-link" href="#main">Skip to content</a>
<header class="header is-stuck" id="header">
    <div class="container header__inner">
        <a class="brand" href="/" aria-label="The Books Wanderer, home">
            <span class="brand__emblem" aria-hidden="true"></span>
            <span class="brand__name">The Books Wanderer<span class="brand__tagline">Literary boutique</span></span>
        </a>
        <div class="actions">
            <a class="icon-btn" href="/#ereaders" aria-label="Back to e-reader picks">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M19 12H5m6-7-7 7 7 7"/></svg>
            </a>
            <a class="icon-btn" href="/cart.html" id="cartBtn" data-cart-btn aria-label="Shopping cart">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 7h12l-1 12H7L6 7Z"/><path d="M9 7a3 3 0 0 1 6 0"/></svg>
                <span class="cart-count" id="cartCount" data-count="0">0</span>
            </a>
        </div>
    </div>
</header>
<main id="main" class="pdp">
    <div class="container">
        <p class="pdp__crumb"><a href="/">Home</a> · <a href="/#ereaders">E-readers</a> · <span id="pickCrumb">{_esc_text(short)}</span></p>
        <aside class="affiliate-disclosure affiliate-disclosure--page" role="note">
            <p><strong>{_esc_text(disclosure)}</strong></p>
            <p class="affiliate-disclosure__detail">{_esc_text(cat.get("linkDisclosure") or "")}</p>
        </aside>
        <div id="pickRoot" class="pdp__layout" data-ssr-pick="1" data-slug="{_esc(pick.get('slug') or '')}">
            <article class="pdp-ssr" data-ssr="1">
                <p class="eyebrow">{_esc_text(category)} · {_esc_text(merchant)}</p>
                {f'<span class="badge badge--gold">{_esc_text(badge)}</span>' if badge else ""}
                <h1>{_esc_text(title)}</h1>
                {"<p class=\"pdp__blurb\">" + _esc_text(blurb) + "</p>" if blurb else ""}
                {"<p class=\"pdp__desc\">" + _esc_text(desc) + "</p>" if desc else ""}
                {f'<img src="{_esc(hero)}" alt="{_esc(title)}" width="800" height="800" style="max-width:min(100%,420px);height:auto;background:#fff;border-radius:12px">' if hero else ""}
                {f"<section><h2>Highlights</h2><ul class=\"pick-bullets\">{bullet_html}</ul></section>" if bullet_html else ""}
                {f"<section><h2>Gallery</h2><div>{gallery}</div></section>" if gallery else ""}
                <section class="pick-cta" style="margin-top:1.5rem">
                    <p><a class="btn pick-cta__btn" href="{_esc(amazon)}" target="_blank" rel="nofollow sponsored noopener">View on Amazon</a></p>
                    <p class="pick-cta__meta"><span class="paid-link">({_esc_text(paid)})</span> · Sold by Amazon · Price shown on Amazon</p>
                    <p class="pick-cta__note">You will leave The Books Wanderer and open Amazon.com. {_esc_text(disclosure)}</p>
                </section>
                {f'<section class="pick-pairs"><p class="eyebrow">Pairs with our shop</p><div class="pick-pairs__list">{pairs_html}</div></section>' if pairs_html else ""}
            </article>
        </div>
    </div>
</main>
<footer class="footer" style="margin-top:var(--sp-8)">
    <div class="container">
        <nav class="footer__links" aria-label="Footer">
            <a href="/about.html">About</a>
            <a href="/guides/hold-a-book-open-one-handed/">Holding a book open</a>
            <a href="/shipping-returns.html">Shipping &amp; returns</a>
            <a href="/contact.html">Contact</a>
            <a href="/privacy.html">Privacy &amp; cookies</a>
        </nav>
        <div class="footer__bottom" style="border:0;padding-top:var(--sp-5)">
        <p class="footer__quote">“For those who wander between pages.”</p>
        <p class="footer__affiliate">{_esc_text(disclosure)}</p>
        <p class="footer__legal">&copy; 2026 The Books Wanderer · {_esc_text(title)}</p>
    </div>
    </div>
</footer>
<script src="/track.js?v=4" defer></script>
<script src="/cart.js?v=3" defer></script>
<script src="/affiliate-data.js?v=5" defer></script>
<script src="/pick.js?v=5" defer></script>
</body>
</html>
"""


def render_pick_not_found(slug: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><title>Pick not found | The Books Wanderer</title>
<meta name="robots" content="noindex,follow">
</head><body class="container" style="padding:2rem">
<h1>Pick not found</h1>
<p>We could not find “{_esc_text(slug)}”.</p>
<p><a href="/#ereaders">Browse e-reader picks</a></p>
</body></html>
"""


def _site_header(*, back_href: str = "/products/", back_label: str = "Back to shop") -> str:
    return f"""
<header class="header is-stuck" id="header">
    <div class="container header__inner">
        <a class="brand" href="/" aria-label="The Books Wanderer, home">
            <span class="brand__emblem" aria-hidden="true"></span>
            <span class="brand__name">
                The Books Wanderer
                <span class="brand__tagline">Literary boutique</span>
            </span>
        </a>
        <nav class="nav" id="nav" aria-label="Primary" style="display:none"></nav>
        <div class="actions">
            <a class="icon-btn" href="{_esc(back_href)}" aria-label="{_esc(back_label)}">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M19 12H5m6-7-7 7 7 7"/></svg>
            </a>
            <a class="icon-btn" href="/cart.html" id="cartBtn" data-cart-btn aria-label="Shopping cart">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 7h12l-1 12H7L6 7Z"/><path d="M9 7a3 3 0 0 1 6 0"/></svg>
                <span class="cart-count" id="cartCount" data-count="0" aria-hidden="true">0</span>
            </a>
        </div>
    </div>
</header>""".strip()


def _site_footer(*, note: str = "") -> str:
    note_html = f"<p class=\"footer__legal\">{_esc_text(note)}</p>" if note else ""
    return f"""
<footer class="footer" style="margin-top:var(--sp-8)">
    <div class="container footer__bottom" style="border:0;padding-top:var(--sp-5)">
        <p class="footer__quote">“For those who wander between pages.”</p>
        <p class="footer__affiliate">As an Amazon Associate I earn from qualifying purchases.</p>
        {note_html}
        <p class="footer__legal">&copy; 2026 The Books Wanderer</p>
    </div>
</footer>""".strip()


def render_collection_page(
    cat: dict[str, Any],
    products: list[dict[str, Any]],
    *,
    canonical: str,
    all_cats: list[dict[str, Any]] | None = None,
) -> str:
    """SSR landing page for /collections/{slug}."""
    name = cat.get("name") or "Collection"
    h1 = cat.get("h1") or name
    page_title = f"{name} | The Books Wanderer"
    short = (cat.get("description") or "").strip()
    meta_src = (cat.get("meta_description") or short or h1).strip()
    meta_desc = _meta_description(meta_src)
    intro_paras = cat.get("intro") or ([short] if short else [])
    slug = cat.get("slug") or ""
    n = len(products)
    count_label = "No pieces yet" if n == 0 else ("1 piece" if n == 1 else f"{n} pieces")

    intro_html = "".join(f"<p>{_esc_text(p)}</p>" for p in intro_paras if p)
    cards = "\n".join(_product_card_html(p) for p in products) or (
        '<p class="catalog-empty">Nothing in this collection yet — '
        '<a href="/products/">browse the full catalog</a>.</p>'
    )

    # Sibling collections for internal links
    siblings = ""
    for c in all_cats or []:
        if c.get("slug") == slug:
            continue
        siblings += (
            f'<a class="collection-chip" href="/collections/{_esc(c.get("slug"))}">'
            f'{_esc_text(c.get("name") or c.get("slug"))}</a> '
        )

    # Prefer first product image for OG when available
    og_img = ""
    for p in products:
        u = p.get("image_url") or ""
        if u:
            og_img = u if str(u).startswith("http") else PUBLIC_BASE + str(u)
            break

    item_list = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": h1,
        "description": meta_src,
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": "The Books Wanderer", "url": PUBLIC_BASE + "/"},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": n,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "url": f"{PUBLIC_BASE}/products/{p.get('slug')}",
                    "name": p.get("title") or p.get("slug"),
                }
                for i, p in enumerate(products)
            ],
        },
    }
    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": PUBLIC_BASE + "/"},
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Collections",
                "item": PUBLIC_BASE + "/collections",
            },
            {"@type": "ListItem", "position": 3, "name": name, "item": canonical},
        ],
    }
    ld_page = json.dumps(item_list, ensure_ascii=False)
    ld_crumbs = json.dumps(crumbs, ensure_ascii=False)
    v = _css_ver()
    social = _social_head(
        title=page_title,
        description=meta_desc,
        canonical=canonical,
        image=og_img,
        og_type="website",
        image_alt=h1,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(page_title)}</title>
    <meta name="description" content="{_esc(meta_desc)}">
    <meta name="robots" content="index,follow,max-image-preview:large">
    <link rel="canonical" href="{_esc(canonical)}">
    {social}
    <meta name="theme-color" content="#f8f2e5">
    <link rel="icon" href="/assets/favicon.ico" sizes="any">
    <link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
    <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png" sizes="180x180">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;1,500&family=Karla:wght@400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/styles.css?v={_esc(v)}">
    <script type="application/ld+json">{ld_page}</script>
    <script type="application/ld+json">{ld_crumbs}</script>
</head>
<body class="page-collection">
<a class="skip-link" href="#main">Skip to content</a>
{_site_header(back_href="/collections", back_label="All collections")}
<main id="main">
  <section class="section collection-hero">
    <div class="container">
      <nav class="pdp__crumb" aria-label="Breadcrumb">
        <a href="/">Home</a> · <a href="/collections">Collections</a> · <span>{_esc_text(name)}</span>
      </nav>
      <p class="eyebrow">Collection · {_esc_text(count_label)}</p>
      <h1>{_esc_text(h1)}</h1>
      <div class="collection-intro">
        {intro_html}
      </div>
      {"<p class=\"collection-siblings\"><span class=\"eyebrow\">Also browse</span> " + siblings + "</p>" if siblings else ""}
    </div>
  </section>
  <section class="section section--sunken" aria-labelledby="collectionGridTitle">
    <div class="container">
      <div class="section__head">
        <div>
          <p class="eyebrow">In this collection</p>
          <h2 id="collectionGridTitle">{_esc_text(name)}</h2>
        </div>
        <a class="link-more" href="/products/">Full catalog</a>
      </div>
      <div class="products is-visible" id="collectionGrid">
        {cards}
      </div>
    </div>
  </section>
</main>
{_site_footer(note=name)}
<script src="/track.js?v=4" defer></script>
<script src="/cart.js?v=3" defer></script>
</body>
</html>
"""


def render_catalog_page(
    products: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    *,
    canonical: str,
) -> str:
    """SSR index of the whole catalog.

    This is the destination every "shop all" link needs: before it existed they
    all pointed at the #featured anchor on the home page, which meant the store
    had no browsable URL of its own.
    """
    n = len(products)
    count_label = "No pieces yet" if n == 0 else ("1 piece" if n == 1 else f"{n} pieces")
    page_title = "Shop all | The Books Wanderer"
    meta_desc = _meta_description(
        "Every piece in the shop: bookmarks, page holders, e-reader sleeves and "
        "reading-nook decor, hand-picked and kept few on purpose."
    )

    chips = '<span class="collection-chip is-active" aria-current="page">All ' + str(n) + "</span>"
    for c in categories:
        cn = int(c.get("product_count") or 0)
        if not cn:
            continue
        chips += (
            f'<a class="collection-chip" href="/collections/{_esc(c.get("slug"))}">'
            f'{_esc_text(c.get("name") or c.get("slug"))} {cn}</a>'
        )

    cards = chr(10).join(_product_card_html(p) for p in products) or (
        '<p class="catalog-empty">Nothing in the shop yet — '
        '<a href="/collections">browse the collections</a>.</p>'
    )

    og_img = ""
    for p in products:
        u = p.get("image_url") or ""
        if u:
            og_img = u if str(u).startswith("http") else PUBLIC_BASE + str(u)
            break

    item_list = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Shop all",
        "description": meta_desc,
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": "The Books Wanderer", "url": PUBLIC_BASE + "/"},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": n,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "url": f"{PUBLIC_BASE}/products/{p.get('slug')}",
                    "name": p.get("title") or p.get("slug"),
                }
                for i, p in enumerate(products)
            ],
        },
    }
    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": PUBLIC_BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Shop", "item": canonical},
        ],
    }
    ld_page = json.dumps(item_list, ensure_ascii=False)
    ld_crumbs = json.dumps(crumbs, ensure_ascii=False)
    v = _css_ver()
    social = _social_head(
        title=page_title,
        description=meta_desc,
        canonical=canonical,
        image=og_img,
        og_type="website",
        image_alt="The Books Wanderer catalog",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(page_title)}</title>
    <meta name="description" content="{_esc(meta_desc)}">
    <meta name="robots" content="index,follow,max-image-preview:large">
    <link rel="canonical" href="{_esc(canonical)}">
    {social}
    <meta name="theme-color" content="#f8f2e5">
    <link rel="icon" href="/assets/favicon.ico" sizes="any">
    <link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
    <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png" sizes="180x180">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;1,500&family=Karla:wght@400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/styles.css?v={_esc(v)}">
    <script type="application/ld+json">{ld_page}</script>
    <script type="application/ld+json">{ld_crumbs}</script>
</head>
<body class="page-collection">
<a class="skip-link" href="#main">Skip to content</a>
{_site_header(back_href="/", back_label="Home")}
<main id="main">
  <section class="section collection-hero">
    <div class="container">
      <nav class="pdp__crumb" aria-label="Breadcrumb">
        <a href="/">Home</a> · <span>Shop</span>
      </nav>
      <p class="eyebrow">Shop · {_esc_text(count_label)}</p>
      <h1>Everything on the shelf</h1>
      <div class="collection-intro">
        <p>The whole catalogue on one page. We keep it small on purpose — every
        piece is chosen by hand, and shipping is already inside the price.</p>
      </div>
      <p class="collection-siblings"><span class="eyebrow">Browse by</span> {chips}</p>
    </div>
  </section>
  <section class="section section--sunken" aria-labelledby="catalogGridTitle">
    <div class="container">
      <div class="section__head">
        <div>
          <p class="eyebrow">All pieces</p>
          <h2 id="catalogGridTitle">Shop all</h2>
        </div>
        <a class="link-more" href="/collections">Browse collections</a>
      </div>
      <div class="products is-visible" id="catalogGrid">
        {cards}
      </div>
    </div>
  </section>
</main>
{_site_footer(note="Shop")}
<script src="/track.js?v=4" defer></script>
<script src="/cart.js?v=3" defer></script>
</body>
</html>
"""


def render_collections_index(
    categories: list[dict[str, Any]],
    *,
    canonical: str,
) -> str:
    """SSR index of all collections."""
    page_title = "Collections | The Books Wanderer"
    meta_desc = _meta_description(
        "Browse book accessories, reading-nook decor, and e-reader gear at "
        "The Books Wanderer literary boutique."
    )
    cards = []
    for c in categories:
        slug = c.get("slug") or ""
        n = int(c.get("product_count") or 0)
        count = "Coming soon" if n == 0 else (f"{n} product" if n == 1 else f"{n} products")
        tile = c.get("tile") or "linear-gradient(150deg, #2b5240, #10241a)"
        cards.append(
            f"""
<a class="category" href="/collections/{_esc(slug)}" style="--tile: {_esc(tile)}">
  <span class="category__count">{_esc_text(count)}</span>
  <h2 class="category__title">{_esc_text(c.get("name") or slug)}</h2>
  <p>{_esc_text(c.get("description") or "")}</p>
</a>"""
        )
    item_list = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Collections",
        "url": canonical,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(categories),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "url": f"{PUBLIC_BASE}/collections/{c.get('slug')}",
                    "name": c.get("name"),
                }
                for i, c in enumerate(categories)
            ],
        },
    }
    v = _css_ver()
    social = _social_head(
        title=page_title,
        description=meta_desc,
        canonical=canonical,
        image_alt="The Books Wanderer collections",
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(page_title)}</title>
    <meta name="description" content="{_esc(meta_desc)}">
    <meta name="robots" content="index,follow,max-image-preview:large">
    <link rel="canonical" href="{_esc(canonical)}">
    {social}
    <meta name="theme-color" content="#f8f2e5">
    <link rel="icon" href="/assets/favicon.ico" sizes="any">
    <link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
    <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png" sizes="180x180">
    <link rel="stylesheet" href="/styles.css?v={_esc(v)}">
    <script type="application/ld+json">{json.dumps(item_list, ensure_ascii=False)}</script>
</head>
<body class="page-collection">
<a class="skip-link" href="#main">Skip to content</a>
{_site_header()}
<main id="main">
  <section class="section">
    <div class="container">
      <nav class="pdp__crumb" aria-label="Breadcrumb">
        <a href="/">Home</a> · <span>Collections</span>
      </nav>
      <p class="eyebrow">Browse by</p>
      <h1>Collections</h1>
      <p class="collection-intro">
        Three small shelves: tools for paper books, pieces for the reading corner,
        and sleeves for the e-readers we recommend.
      </p>
      <div class="categories" style="margin-top:var(--sp-6)">
        {"".join(cards)}
      </div>
      <p style="margin-top:var(--sp-6)"><a class="link-more" href="/products/">View full catalog</a></p>
    </div>
  </section>
</main>
{_site_footer()}
<script src="/track.js?v=4" defer></script>
<script src="/cart.js?v=3" defer></script>
</body>
</html>
"""


def render_collection_not_found(slug: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><title>Collection not found | The Books Wanderer</title>
<meta name="robots" content="noindex,follow">
<link rel="stylesheet" href="/styles.css?v={_esc(_css_ver())}">
</head><body class="container" style="padding:2rem">
<h1>Collection not found</h1>
<p>We could not find “{_esc_text(slug)}”.</p>
<p><a href="/collections">All collections</a> · <a href="/products/">Full catalog</a></p>
</body></html>
"""


def _category_tile_html(c: dict[str, Any]) -> str:
    n = int(c.get("product_count") or 0)
    count = "Coming soon" if n == 0 else ("1 product" if n == 1 else f"{n} products")
    tile = c.get("tile") or "linear-gradient(150deg, #2b5240, #10241a)"
    slug = c.get("slug") or ""
    return f"""
<a class="category" href="/collections/{_esc(slug)}" style="--tile: {_esc(tile)}" data-ssr-cat="1">
  <span class="category__count">{_esc_text(count)}</span>
  <h3>{_esc_text(c.get("name") or slug)}</h3>
  <p>{_esc_text(c.get("description") or "")}</p>
</a>"""


SIZES_CARD = "(max-width: 780px) 45vw, 300px"
SIZES_THUMB = "(max-width: 780px) 45vw, 380px"
SIZES_PDP_HERO = "(max-width: 780px) 92vw, 420px"


def _cj_variant(url: str, width: int, *, webp: bool = True) -> str:
    """Ask CJ's CDN for a resized copy of one of their images.

    Their bucket honours Alibaba OSS's x-oss-process, so a 743 KB original
    comes back as a 34 KB 600px WebP. Without it the grid ships full-resolution
    originals (800-1363px) into cards that render around 268px wide.
    """
    if not url or "cjdropshipping.com" not in url or "x-oss-process" in url:
        return url
    sep = "&" if "?" in url else "?"
    chain = f"image/resize,w_{width}"
    if webp:
        chain += "/format,webp"
    return f"{url}{sep}x-oss-process={chain}"


def _cj_img_attrs(
    url: str,
    *,
    base_w: int = 600,
    widths: tuple[int, ...] = (400, 600, 900),
    sizes: str = SIZES_CARD,
) -> str:
    """src + srcset + sizes for a CJ image; a plain src for anything else."""
    if not url or "cjdropshipping.com" not in url:
        return f'src="{_esc(url)}"'
    srcset = ", ".join(f"{_esc(_cj_variant(url, w))} {w}w" for w in widths)
    return (
        f'src="{_esc(_cj_variant(url, base_w))}" '
        f'srcset="{srcset}" sizes="{_esc(sizes)}"'
    )


def _product_card_html(p: dict[str, Any]) -> str:
    title = p.get("title") or "Product"
    slug = p.get("slug") or ""
    href = f"/products/{_esc(slug)}"
    img = p.get("image_url") or ""
    if img.startswith("/"):
        img = PUBLIC_BASE + img
    cat = p.get("category") or "Collection"
    price = p.get("price_usd")
    price_s = f"${float(price):.2f} USD" if price is not None else ""
    desc = (p.get("description") or "")[:140]
    nvar = int(p.get("variant_count") or 0)
    badge = f'<span class="badge badge--gold">{nvar} designs</span>' if nvar > 1 else ""
    img_tag = (
        f'<img {_cj_img_attrs(img)} alt="{_esc(title)}" width="600" height="750" loading="lazy" decoding="async">'
        if img
        else ""
    )
    return f"""
<article class="product" data-ssr-card="1" data-category="{_esc(p.get("category_slug") or "")}">
  <a class="product__link" href="{href}" aria-label="View {_esc(title)}">
    <div class="product__media">{badge}{img_tag}</div>
  </a>
  <div class="product__body">
    <p class="product__cat">{_esc_text(cat)}</p>
    <h3><a href="{href}">{_esc_text(title)}</a></h3>
    {"<p class=\"product__price\"><strong>" + _esc_text(price_s) + "</strong></p>" if price_s else ""}
    {"<p class=\"product__blurb-sm\">" + _esc_text(desc) + "</p>" if desc else ""}
    <a class="add-to-cart" href="{href}">{"Choose design" if nvar > 1 else "View details"}</a>
  </div>
</article>"""


def _affiliate_card_html(p: dict[str, Any], *, paid_label: str = "paid link") -> str:
    title = p.get("shortTitle") or p.get("title") or "E-reader"
    slug = p.get("slug") or ""
    detail = f"/picks/{_esc(slug)}"
    img = p.get("imageUrl") or ""
    blurb = p.get("blurb") or ""
    amazon = p.get("amazonUrl") or "#"
    badge = p.get("badge") or ""
    badge_html = f'<span class="badge badge--gold">{_esc_text(badge)}</span>' if badge else ""
    return f"""
<article class="product product--affiliate" data-ssr-card="1">
  <a class="product__link" href="{detail}" aria-label="View {_esc(title)}">
    <div class="product__media pick-media">{badge_html}
      <img src="{_esc(img)}" alt="{_esc(title)}" width="600" height="600" loading="lazy">
    </div>
  </a>
  <div class="product__body">
    <p class="product__cat">{_esc_text(p.get("merchant") or "Amazon")} · {_esc_text(p.get("category") or "E-readers")}</p>
    <h3><a href="{detail}">{_esc_text(title)}</a></h3>
    <p class="product__blurb-sm">{_esc_text(blurb)}</p>
    <p class="product__price product__price--note"><strong>See price on Amazon</strong></p>
    <a class="add-to-cart" href="{_esc(amazon)}" target="_blank" rel="nofollow sponsored noopener">View on Amazon</a>
    <p class="paid-link-note"><span class="paid-link">({_esc_text(paid_label)})</span> · Affiliate</p>
  </div>
</article>"""


# Christmas shelf on the home page, in display order. The section is
# dropped from the page when none of these are live.
CHRISTMAS_SLUGS = (
    "twilight-library-book-nook-kit",
    "book-lovers-advent-calendar",
    "book-tree-christmas-ornament",
    "bookshelf-lantern-light",
    "baker-street-book-nook-kit",
    "heart-bookshelf-ornament",
    "christmas-magnetic-bookmarks",
    "reading-log-bookmarks",
)


def _inject_christmas_shelf(html_doc: str, products: list[dict[str, Any]]) -> str:
    start, end = "<!-- christmas:start -->", "<!-- christmas:end -->"
    if start not in html_doc:
        return html_doc
    by_slug = {p.get("slug"): p for p in products}
    gifts = [by_slug[s] for s in CHRISTMAS_SLUGS if s in by_slug]
    if not gifts:
        head, _, rest = html_doc.partition(start)
        return head + rest.partition(end)[2]
    cards = "\n".join(_product_card_html(p) for p in gifts)
    return html_doc.replace("<!-- christmas-gifts -->", cards, 1)


def inject_home_seo(
    html_doc: str,
    *,
    products: list[dict[str, Any]],
    affiliate: dict[str, Any] | None = None,
    categories: list[dict[str, Any]] | None = None,
) -> str:
    """Inject crawlable product + affiliate + category cards into index.html."""
    aff = affiliate or load_affiliate_catalog()
    paid = aff.get("paidLinkLabel") or "paid link"
    prod_html = "\n".join(_product_card_html(p) for p in products)
    aff_html = "\n".join(
        _affiliate_card_html(p, paid_label=paid) for p in (aff.get("products") or [])
    )
    cat_html = "\n".join(_category_tile_html(c) for c in (categories or []))
    embed = (
        f'<script type="application/json" id="affiliate-products-json">'
        f"{json.dumps(aff, ensure_ascii=False)}"
        f"</script>"
    )

    html_doc = _inject_christmas_shelf(html_doc, products)
    if prod_html:
        html_doc = html_doc.replace(
            '<p class="catalog-loading" id="catalogLoading">Loading products…</p>',
            prod_html,
            1,
        )
    if aff_html:
        html_doc = html_doc.replace(
            '<p class="catalog-loading">Loading e-reader picks…</p>',
            aff_html,
            1,
        )
    if cat_html:
        # Empty categories container — inject crawlable links to /collections/*
        html_doc = html_doc.replace(
            '<div class="categories reveal" id="categoryTiles" aria-busy="true">\n'
            "                <!-- Filled from /api/categories -->\n"
            "            </div>",
            f'<div class="categories reveal is-visible" id="categoryTiles" aria-busy="false">\n'
            f"{cat_html}\n"
            f"            </div>",
            1,
        )

    # Embed affiliate JSON before affiliate-data.js
    if "affiliate-products-json" not in html_doc:
        html_doc = html_doc.replace(
            '<script src="affiliate-data.js',
            embed + '\n<script src="affiliate-data.js',
            1,
        )
    # Ensure absolute OG / logo URLs when template used relative paths
    html_doc = html_doc.replace(
        'content="assets/og-default.jpg"',
        f'content="{PUBLIC_BASE}/assets/og-default.jpg"',
    )
    html_doc = html_doc.replace(
        'content="assets/logo.png"',
        f'content="{PUBLIC_BASE}/assets/og-default.jpg"',
    )
    html_doc = html_doc.replace(
        f'"image": "{PUBLIC_BASE}/assets/logo.png"',
        f'"image": "{PUBLIC_BASE}/assets/og-default.jpg"',
    )
    return html_doc
