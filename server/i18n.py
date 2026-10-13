"""Spanish edition of the shop, served under /es/.

English stays the default and the source of truth. A Spanish page is the
English page rendered from Spanish product/category data and then passed
through `localize()`, which:

* sets <html lang="es"> and makes relative asset paths absolute (the page
  now lives one directory deeper);
* prefixes links to pages that have a Spanish edition with /es/;
* swaps UI strings using i18n/es.json (exact text nodes and attributes,
  plus a few patterns with numbers or names in them);
* adds hreflang alternates and the language switcher (both editions).

Strings missing from the dictionary simply stay in English, so a new
English paragraph never breaks the Spanish page.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PUBLIC_BASE = "https://thebookswanderer.com"
LANGS = ("en", "es")

# Pages that exist in both languages. Anything else (guides, picks, api,
# assets) keeps its single English URL.
_LOCALIZED = re.compile(
    r"^/(?:$|index\.html$|#|products/|collections(?:/|$)|"
    r"(?:about|contact|privacy|shipping-returns|cart|checkout)\.html)"
)
I18N_JS_VERSION = "2"
STATIC_PAGES = ("about", "contact", "privacy", "shipping-returns", "cart", "checkout")


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    raw = json.loads((ROOT / "i18n" / "es.json").read_text(encoding="utf-8"))
    templates = [
        (re.compile(pat), re.sub(r"\$(\d)", r"\\\1", rep)) for pat, rep in raw.get("templates", [])
    ]
    return {**raw, "_templates": templates}


@lru_cache(maxsize=1)
def _products() -> dict[str, dict[str, str]]:
    path = ROOT / "i18n" / "products_es.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lang_of(path: str) -> str:
    return "es" if path == "/es" or path.startswith("/es/") else "en"


def is_localized(path: str) -> bool:
    return bool(_LOCALIZED.match(path))


def en_path(path: str) -> str:
    """/es/products/x -> /products/x"""
    if path == "/es" or path == "/es/":
        return "/"
    return path[3:] if path.startswith("/es/") else path


def path_for(path: str, lang: str) -> str:
    """English path -> same page in `lang`."""
    path = en_path(path)
    if lang != "es" or not is_localized(path):
        return path
    if path in ("/", "/index.html"):
        return "/es/"
    return "/es" + path


def url_for(path: str, lang: str) -> str:
    return PUBLIC_BASE + path_for(path, lang)


# ── Data overlays ─────────────────────────────────────────────────────────


def category(c: dict[str, Any], lang: str) -> dict[str, Any]:
    if lang != "es":
        return c
    es = _data().get("categories", {}).get(c.get("slug") or "", {})
    return {**c, **es}


def category_name(slug: str, fallback: str, lang: str) -> str:
    if lang != "es":
        return fallback
    return _data().get("categories", {}).get(slug, {}).get("name") or fallback


def product(p: dict[str, Any], lang: str) -> dict[str, Any]:
    """Spanish title/description over a to_public()/to_detail() dict."""
    if lang != "es" or not p:
        return p
    es = _products().get(p.get("slug") or "", {})
    out = dict(p)
    if es.get("title"):
        out["title"] = es["title"]
    if es.get("description"):
        out["description"] = es["description"]
    # Localized mockups (e.g. a printable whose pages are in Spanish).
    if es.get("image_url"):
        out["image_url"] = es["image_url"]
    if es.get("gallery") and "lifestyle_images" in out:
        out["images"] = out["lifestyle_images"] = list(es["gallery"])
    if es.get("default_variant") and out.get("variants"):
        variants = list(out["variants"])
        first = [v for v in variants if v.get("name") == es["default_variant"]]
        if first:
            out["variants"] = first + [v for v in variants if v is not first[0]]
            out["default_variant_id"] = first[0].get("id")
    cat_slug = out.get("category_slug") or ""
    if cat_slug and out.get("category"):
        out["category"] = category_name(cat_slug, out["category"], lang)
    return out


def product_title(slug: str, fallback: str, lang: str) -> str:
    if lang != "es":
        return fallback
    return _products().get(slug, {}).get("title") or fallback


# ── HTML pass ─────────────────────────────────────────────────────────────

_SKIP_BLOCK = re.compile(r"(<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>)", re.S | re.I)
_TEXT = re.compile(r">([^<]+)<")
_ATTR = re.compile(r'(\s(?:alt|aria-label|placeholder|title|content)=")([^"]*)(")')
_HREF = re.compile(r'(\s(?:href|src|action)=")([^"]*)(")')
_ABS = re.compile(re.escape(PUBLIC_BASE) + r'(/[^"\s<>\\]*)')


def translate(text: str) -> str | None:
    """Spanish for one UI string, or None when there is none."""
    norm = " ".join(text.split())
    if not norm:
        return None
    d = _data()
    hit = d["phrases"].get(norm)
    if hit is not None:
        return hit
    for pat, rep in d["_templates"]:
        m = pat.fullmatch(norm)
        if m:
            return m.expand(rep)
    return None


def _swap_text(m: re.Match) -> str:
    import html as _html

    raw = m.group(1)
    es = translate(_html.unescape(raw))
    if es is None:
        return m.group(0)
    lead = raw[: len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()):]
    return f">{lead}{_html.escape(es, quote=False)}{trail}<"


def _swap_attr(m: re.Match) -> str:
    val = m.group(2)
    if val.startswith(("http", "/", "#")):
        return m.group(0)
    import html as _html

    es = translate(_html.unescape(val))
    if es is None:
        return m.group(0)
    return f"{m.group(1)}{_html.escape(es, quote=True)}{m.group(3)}"


def _rewrite_href(m: re.Match) -> str:
    val = m.group(2)
    if not val or val.startswith(("#", "http", "mailto:", "tel:", "data:", "javascript:", "//")):
        return m.group(0)
    if not val.startswith("/"):
        val = "/" + val
    if not val.startswith("/es/") and is_localized(val):
        val = path_for(val, "es")
    return f"{m.group(1)}{val}{m.group(3)}"


def _rewrite_abs(m: re.Match) -> str:
    path = m.group(1)
    if "#organization" in path or path.startswith("/es/") or not is_localized(path):
        return m.group(0)
    return PUBLIC_BASE + path_for(path, "es")


def _alternates(en: str) -> str:
    links = [
        f'<link rel="alternate" hreflang="en" href="{url_for(en, "en")}">',
        f'<link rel="alternate" hreflang="es" href="{url_for(en, "es")}">',
        f'<link rel="alternate" hreflang="x-default" href="{url_for(en, "en")}">',
    ]
    return "\n    ".join(links)


def _switcher(en: str, lang: str) -> str:
    other = "es" if lang == "en" else "en"
    label = "ES" if other == "es" else "EN"
    title = "Ver en español" if other == "es" else "View in English"
    return (
        f'<a class="lang-switch" href="{path_for(en, other)}" hreflang="{other}" lang="{other}" '
        f'data-lang-switch="{other}" title="{title}">{label}</a>'
    )


def localize(doc: str, lang: str, path: str) -> str:
    """Finish a page for `lang`. `path` is the English path of the page."""
    en = en_path(path)
    has_alt = is_localized(en)

    if lang == "es":
        doc = re.sub(r'\s*<link rel="alternate" hreflang="[^"]*" href="[^"]*">', "", doc)
        parts = _SKIP_BLOCK.split(doc)
        out = []
        for i, part in enumerate(parts):
            if i % 2:  # script / style block: only its src, and JSON-LD URLs
                part = re.sub(r"^<script\b[^>]*>", lambda t: _HREF.sub(_rewrite_href, t.group(0)), part)
                if 'type="application/ld+json"' in part:
                    part = _ABS.sub(_rewrite_abs, part)
                out.append(part)
                continue
            part = _HREF.sub(_rewrite_href, part)
            part = _ABS.sub(_rewrite_abs, part)
            part = _TEXT.sub(_swap_text, part)
            part = _ATTR.sub(_swap_attr, part)
            out.append(part)
        doc = "".join(out)
        doc = re.sub(r'<html lang="en"', '<html lang="es"', doc, count=1)
        doc = doc.replace(
            "<head>",
            "<head>\n<script>window.TBW_I18N=" + i18n_payload() + ";</script>",
            1,
        )

    if has_alt and 'hreflang="es"' not in doc:
        doc = re.sub(
            r'(<link rel="canonical"[^>]*>)',
            lambda m: m.group(1) + "\n    " + _alternates(en),
            doc,
            count=1,
        )
    if "/i18n.js" not in doc:
        doc = doc.replace("</head>", f'<script src="/i18n.js?v={I18N_JS_VERSION}"></script>\n</head>', 1)
    if has_alt and "data-lang-switch" not in doc:
        doc = doc.replace('<div class="actions">', '<div class="actions">\n' + _switcher(en, lang), 1)
    return doc


@lru_cache(maxsize=1)
def i18n_payload() -> str:
    """Dictionary for i18n.js (client-rendered parts of the page)."""
    d = _data()
    payload = {
        "phrases": d["phrases"],
        "templates": d.get("templates", []),
    }
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
