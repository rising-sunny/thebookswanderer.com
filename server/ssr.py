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


def _social_head(
    *,
    title: str,
    description: str,
    canonical: str,
    image: str = "",
    og_type: str = "website",
    site_name: str = "The Books Wanderer",
) -> str:
    """Shared Open Graph + Twitter tags (aligned with title/description)."""
    img = image or f"{PUBLIC_BASE}/assets/logo.png"
    if img.startswith("/"):
        img = PUBLIC_BASE + img
    lines = [
        f'<meta property="og:type" content="{_esc(og_type)}">',
        f'<meta property="og:site_name" content="{_esc(site_name)}">',
        f'<meta property="og:title" content="{_esc(title)}">',
        f'<meta property="og:description" content="{_esc(description)}">',
        f'<meta property="og:url" content="{_esc(canonical)}">',
        f'<meta property="og:image" content="{_esc(img)}">',
        f'<meta property="og:locale" content="en_US">',
        f'<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{_esc(title)}">',
        f'<meta name="twitter:description" content="{_esc(description)}">',
        f'<meta name="twitter:image" content="{_esc(img)}">',
    ]
    return "\n    ".join(lines)


def render_product_page(detail: dict[str, Any], *, canonical: str) -> str:
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
    variants = detail.get("variants") or []
    lifestyle = detail.get("lifestyle_images") or detail.get("images") or []

    if price is not None and price_max is not None and float(price_max) > float(price):
        price_block = f"${float(price):.2f}–${float(price_max):.2f} USD"
    elif price is not None:
        price_block = f"${float(price):.2f} USD"
    else:
        price_block = ""

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
        json_ld_product["offers"] = {
            "@type": "Offer",
            "url": canonical,
            "priceCurrency": "USD",
            "price": f"{float(price):.2f}",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": "The Books Wanderer"},
        }

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
                "item": PUBLIC_BASE + "/#featured",
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
                f'<img src="{_esc(s)}" alt="{_esc(title)} lifestyle photo {i + 1}" '
                f'width="400" height="400" loading="lazy" '
                f'style="max-width:48%;height:auto;margin:0.25rem;border-radius:8px">'
            )
        life_bits = (
            '<section class="pdp-ssr__section">'
            "<h2>Product gallery</h2>"
            f"<div>{''.join(imgs)}</div>"
            "</section>"
        )

    hero = (
        f'<img src="{_esc(img)}" alt="{_esc(title)}" width="800" height="1000" '
        f'style="max-width:min(100%,420px);height:auto;border-radius:12px;display:block;margin:1rem 0">'
        if img
        else ""
    )

    # Substantial article body — Google Soft 404 is often thin / empty pages.
    ssr_body = f"""
<article class="pdp-ssr" data-ssr="1" itemscope itemtype="https://schema.org/Product">
  <p class="eyebrow">{_esc_text(category)}</p>
  <h1 itemprop="name">{_esc_text(title)}</h1>
  {"<p class=\"pdp__price\"><strong itemprop=\"offers\" itemscope itemtype=\"https://schema.org/Offer\"><meta itemprop=\"priceCurrency\" content=\"USD\"><span itemprop=\"price\">" + _esc_text(price_block) + "</span></strong></p>" if price_block else ""}
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
      <li>Gift-ready packaging on boutique orders</li>
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
       <a href="/#featured">Browse the full catalog</a> ·
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
    <link rel="icon" href="/assets/logo.png" type="image/png">
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
            <a class="icon-btn" href="/#featured" aria-label="Back to shop">
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
            <a href="/">Home</a> · <a href="/#featured">Shop</a>
            {f' · <a href="/#featured?category={_esc(cat_slug)}">{_esc_text(category)}</a>' if cat_slug else ""}
            · <span id="pdpCrumb">{_esc_text(title)}</span>
        </nav>
        <div id="pdpRoot" class="pdp__layout" data-product-id="{_esc(product_id or "")}" data-slug="{_esc(slug)}">
            {ssr_body}
        </div>
    </div>
</main>
<footer class="footer" style="margin-top:var(--sp-8)">
    <div class="container footer__bottom" style="border:0;padding-top:var(--sp-5)">
        <p class="footer__quote">“For those who wander between pages.”</p>
        <p class="footer__affiliate">As an Amazon Associate I earn from qualifying purchases.</p>
        <p class="footer__legal">&copy; 2026 The Books Wanderer · {_esc_text(title)}</p>
    </div>
</footer>
<script src="/track.js?v=1" defer></script>
<script src="/cart.js?v=2" defer></script>
<script src="/product.js?v=23" defer></script>
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
    <p>Browse our <a href="/#featured">reader catalog</a> for available pieces.</p>
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
        f'<img src="{_esc(u)}" alt="{_esc(title)} photo {i + 1}" width="400" height="400" '
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
            f"/product.html?slug={_esc(x.get('slug'))}" if x.get("slug") else "#"
        )
        # href already needs raw path; escape attr only
        label = x.get("label") or x.get("slug") or "Related"
        pairs_html += (
            f'<a class="pick-pair" href="{_esc(href)}">{_esc_text(label)}</a> '
        )

    json_ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "description": desc,
        "sku": pick.get("asin") or pick.get("slug"),
        "brand": {"@type": "Brand", "name": "Amazon"},
        "url": canonical,
        "offers": {
            "@type": "Offer",
            "url": amazon,
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
            "seller": {"@type": "Organization", "name": "Amazon"},
        },
    }
    if images:
        json_ld["image"] = images[:5]
    elif img:
        json_ld["image"] = [img]

    ld = json.dumps(json_ld, ensure_ascii=False)
    v = _css_ver()
    embed = json.dumps(cat, ensure_ascii=False)
    social = _social_head(
        title=page_title,
        description=meta_desc,
        canonical=canonical,
        image=hero or img,
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
    <link rel="icon" href="/assets/logo.png" type="image/png">
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
        <div id="pickRoot" class="pdp__layout" data-ssr-pick="1">
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
    <div class="container footer__bottom" style="border:0;padding-top:var(--sp-5)">
        <p class="footer__quote">“For those who wander between pages.”</p>
        <p class="footer__affiliate">{_esc_text(disclosure)}</p>
        <p class="footer__legal">&copy; 2026 The Books Wanderer · {_esc_text(title)}</p>
    </div>
</footer>
<script src="/track.js?v=1" defer></script>
<script src="/cart.js?v=2" defer></script>
<script src="/affiliate-data.js?v=5" defer></script>
<script src="/pick.js?v=4" defer></script>
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


def _product_card_html(p: dict[str, Any]) -> str:
    title = p.get("title") or "Product"
    slug = p.get("slug") or ""
    href = f"/product.html?slug={_esc(slug)}"
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
        f'<img src="{_esc(img)}" alt="{_esc(title)}" width="600" height="750" loading="lazy">'
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
    detail = f"/pick.html?slug={_esc(slug)}"
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


def inject_home_seo(
    html_doc: str,
    *,
    products: list[dict[str, Any]],
    affiliate: dict[str, Any] | None = None,
) -> str:
    """Inject crawlable product + affiliate cards into the static index.html shell."""
    aff = affiliate or load_affiliate_catalog()
    paid = aff.get("paidLinkLabel") or "paid link"
    prod_html = "\n".join(_product_card_html(p) for p in products)
    aff_html = "\n".join(
        _affiliate_card_html(p, paid_label=paid) for p in (aff.get("products") or [])
    )
    embed = (
        f'<script type="application/json" id="affiliate-products-json">'
        f"{json.dumps(aff, ensure_ascii=False)}"
        f"</script>"
    )

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

    # Embed affiliate JSON before affiliate-data.js
    if "affiliate-products-json" not in html_doc:
        html_doc = html_doc.replace(
            '<script src="affiliate-data.js',
            embed + '\n<script src="affiliate-data.js',
            1,
        )
    # Absolute OG image
    html_doc = html_doc.replace(
        'content="assets/logo.png"',
        f'content="{PUBLIC_BASE}/assets/logo.png"',
    )
    html_doc = html_doc.replace(
        '"image": "assets/logo.png"',
        f'"image": "{PUBLIC_BASE}/assets/logo.png"',
    )
    return html_doc
