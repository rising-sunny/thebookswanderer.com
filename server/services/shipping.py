"""Live delivery coverage and prices. Quotation endpoints only; no orders.

US standard delivery is already included in the retail price. Other markets
pay only the positive difference against that same basket's US delivery cost.
Country lists are discovery choices, never a promise that an item can ship.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import httpx
from functools import lru_cache

from services import cj, digital, lulu, printify, prodigi_store
from services.countries import COUNTRY_CODES

IMPORT_NOTE = "Import duties or taxes collected by your country on arrival are not included in this total."
_cache = {}


def description(text, supplier, lang="en"):
    """Retire earlier fixed-market promises in stored catalogue descriptions."""
    if supplier == "digital":
        return text
    if lang == "es":
        text = re.sub(r"Disponible solo para entregas en Estados Unidos, con envío estándar (?:gratuito|incluido)\.", "Envío estándar a Estados Unidos incluido. Otros destinos se cotizan antes del pago.", text)
        text = text.replace("solo envíos a direcciones de EE. UU.", "consulta la disponibilidad y el total para tu destino")
        text = text.replace("Envío gratuito a Estados Unidos y los demás destinos habilitados para nuestros libros impresos.", "Envío estándar a Estados Unidos incluido. Otros destinos se cotizan antes del pago.")
        text = re.sub(r"Envío (?:estándar )?gratis a (?:Estados Unidos,|EE\. UU\.,)[^\n]+?Irlanda\.", "Envío estándar a EE. UU. incluido. Otros destinos se cotizan antes del pago.", text, flags=re.I)
        text = re.sub(r"(?:Solo (?:se envía|envíos|entrega)|Envíos solo) a (?:Estados Unidos|EE\. UU\.)[^\n]*?(?:\. |$)", "Consulta la disponibilidad y el total para tu destino antes del pago. ", text, flags=re.I)
        text = text.replace("envío gratis a todo el mundo", "envío internacional sujeto a cotización")
        if supplier == "printify":
            text = text.replace("Entrega estimada:", "Entrega estándar estimada en Estados Unidos:")
        return text
    text = re.sub(r"Free shipping to the United States, United Kingdom,[^\n]+?Ireland\.", "Standard US shipping included. Other destinations quoted before payment.", text, flags=re.I)
    text = re.sub(r"US delivery only(?:, with standard shipping included|; free standard shipping)?\.", "Standard US shipping included. Other destinations quoted before payment.", text)
    text = text.replace("ships to US addresses only", "check your destination for delivery availability and the total")
    text = text.replace("Shipping is already inside the price.", "Standard US shipping is included; other destinations are quoted before payment.")
    text = text.replace("the price already includes the shipping", "the price includes standard US shipping")
    text = re.sub(r"free (?:worldwide shipping|shipping worldwide)", "international shipping quoted before payment", text, flags=re.I)
    if supplier == "printify":
        text = text.replace("estimated delivery", "estimated standard US delivery").replace("Estimated delivery:", "Estimated standard US delivery:")
    return text


class QuoteError(Exception):
    def __init__(self, message, *, status=503, reason="temporarily_unavailable", products=()):
        super().__init__(message)
        self.status, self.reason, self.products = status, reason, list(products)


def amount(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise QuoteError("Delivery could not be calculated. Please try again.") from None
    if not math.isfinite(n) or n < 0:
        raise QuoteError("Delivery could not be calculated. Please try again.")
    return n


async def cached(key, get):
    # Hash addresses; cached results contain rates, not customer addresses.
    key = hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()
    found = _cache.get(key)
    if found and found[0] > time.monotonic():
        return found[1]
    value = await get()
    if len(_cache) >= 512:
        _cache.clear()
    _cache[key] = (time.monotonic() + 300, value)
    return value


def pick_freight(options):
    valid = [o for o in options if o.get("logisticPrice") is not None]
    if not valid:
        raise QuoteError("Delivery is not available for this product to this destination.", status=400, reason="no_route")
    def price(o): return amount(o["logisticPrice"])
    ceiling = min(map(price, valid)) + float(os.getenv("SHIPPING_UPGRADE_MAX_USD", "3"))
    def days(o):
        numbers = re.findall(r"\d+", str(o.get("logisticAging") or ""))
        return max(map(int, numbers)) if numbers else 10**6
    return min((o for o in valid if price(o) <= ceiling), key=lambda o: (days(o), price(o)))


@lru_cache(maxsize=128)
def _pages(path, modified, size):
    from pypdf import PdfReader
    return len(PdfReader(path).pages)


def lulu_line(product, variant, quantity):
    file = digital.file_path(digital.file_for(product, variant))
    if not file:
        raise QuoteError("This book is temporarily unavailable. Please try again later.")
    stat = file.stat()
    return {"pod_package_id": product.lulu_package,
            "page_count": _pages(str(file), stat.st_mtime_ns, stat.st_size), "quantity": quantity}


def surcharge(actual, baseline, country, included_us=True):
    if included_us and country == "US":
        return 0.0
    cost = max(0, actual - baseline) if included_us else actual
    return round(cost * float(os.getenv("SHIPPING_MARKUP", "1.15")), 2)


def unavailable(names):
    return QuoteError("Delivery is not available to this destination for: " + ", ".join(names) + ". Choose another destination or remove these items.",
                      status=400, reason="no_route", products=names)


async def quote(cart, country, address=None, *, free_us=True):
    try:
        return await _quote(cart, country, address, free_us=free_us)
    except httpx.HTTPError:
        raise QuoteError("The delivery service is temporarily unavailable. Please try again before paying.") from None


async def _quote(cart, country, address=None, *, free_us=True):
    country = country.upper()
    if country not in COUNTRY_CODES:
        raise QuoteError("Please select a valid destination country.", status=422, reason="invalid_country")
    address = {k: str(v or "").strip() for k, v in (address or {}).items()}
    groups = {}
    for product, variant, qty in cart:
        supplier = product.supplier or "cj"
        if supplier == "digital":
            continue
        key = (supplier, (product.from_country or "CN").upper() if supplier == "cj" else "")
        groups.setdefault(key, []).append((product, variant, qty))
    legs, shipping_total = [], 0.0
    is_estimate = bool(groups) and not (address.get("street1") and address.get("city"))
    for (supplier, origin), items in groups.items():
        names = [p.title for p, _, _ in items]
        if supplier == "cj":
            lines = [{"vid": (v.cj_vid if v else p.cj_vid), "quantity": q} for p, v, q in items]
            async def freight(dest, postcode=None):
                return await cached(["cj", origin, dest, postcode, lines], lambda: cj.freight_calculate(
                    start_country=origin, end_country=dest, products=lines, zip_code=postcode))
            try:
                options = await freight(country, address.get("postcode"))
                if not options: raise unavailable(names)
                best = pick_freight(options)
                actual = amount(best["logisticPrice"])
                baseline = actual if country == "US" else 0.0
                if free_us and country != "US":
                    base_options = await freight("US", "20540")
                    if base_options: baseline = amount(pick_freight(base_options)["logisticPrice"])
            except cj.CJError:
                raise QuoteError("Delivery could not be calculated right now. Please try again.", products=names) from None
            retail = surcharge(actual, baseline, country, free_us)
            leg = {"supplier": supplier, "from": origin, "logistic_name": best.get("logisticName"),
                   "eta_days": best.get("logisticAging"), "shipping_total": retail}
        elif supplier == "printify":
            lines = [{"product_id": p.printify_product_id, "variant_id": int(v.printify_variant_id if v else 0), "quantity": q} for p, v, q in items]
            addr = {"country": country, "region": printify.region_code(address.get("state", "")) if country == "US" else address.get("state", ""),
                    "zip": address.get("postcode", ""), "city": address.get("city", ""), "address1": address.get("street1", "")}
            addr = {k: val for k, val in addr.items() if val}
            try:
                actual = await cached(["printify", lines, addr], lambda: printify.shipping_cost(lines, country, addr))
                baseline = actual if country == "US" else 0.0
                if free_us and country != "US":
                    baseline = await cached(["printify", lines, "US"], lambda: printify.shipping_cost(lines, "US"))
            except printify.PrintifyError as exc:
                # A transport/auth error must not be presented as a permanent country exclusion.
                if re.search(r"not (?:supported|available)|cannot ship|can't ship|no shipping|unable to ship|shipping.*unavailable", str(exc), re.I):
                    raise unavailable(names) from None
                raise QuoteError("Delivery could not be confirmed for these items and destination. Please check your address or try again.", products=names) from None
            retail = surcharge(actual, baseline, country, free_us)
            leg = {"supplier": supplier, "from": "US", "logistic_name": "Printify Standard", "shipping_total": retail,
                   "eta_days": printify.ETA_DAYS if country == "US" else None}
        elif supplier == "prodigi":
            if country != "US":
                raise unavailable(names)
            try:
                leg = await prodigi_store.shipping(items, country)
            except prodigi_store.ProdigiError:
                raise QuoteError("Delivery could not be confirmed for this print. Please try again later.", products=names) from None
            # Standard US shipping is included in the reviewed retail price.
            # Prodigi's quote is country-level, so require complete address fields at checkout.
            if not all(address.get(k) for k in ("street1", "city", "state", "postcode")):
                is_estimate = True
            retail = leg["shipping_total"]
        elif supplier == "lulu":
            lines = [lulu_line(p, v, q) for p, v, q in items]
            addr = {"country": country, **{k: val for k, val in address.items() if val}}
            if addr.get("state"): addr["state"] = lulu.state_code(country, addr["state"])
            try:
                options = await cached(["lulu-options", lines, addr], lambda: lulu.request("POST", "/shipping-options/", json={"currency": "USD", "line_items": lines, "shipping_address": addr}))
                if not options: raise unavailable(names)
                options = [o for o in options if o.get("cost_excl_tax") is not None and o.get("level") in {"MAIL", "PRIORITY_MAIL", "GROUND", "GROUND_HD", "GROUND_BUS", "EXPEDITED", "EXPRESS"}]
                if not options: raise unavailable(names)
                preferred = (os.getenv("LULU_SHIPPING_LEVEL") or "MAIL").upper()
                best = min(options, key=lambda o: (o.get("level") != preferred, amount(o["cost_excl_tax"])))
                level = best["level"]
                complete = bool(address.get("street1") and address.get("city"))
                actual = amount(best["cost_excl_tax"])
                base_addr = {"country": "US", "state": "DC", "postcode": "20540"}
                base_options = await cached(["lulu-options", lines, base_addr], lambda: lulu.request("POST", "/shipping-options/", json={"currency": "USD", "line_items": lines, "shipping_address": base_addr})) if country != "US" else options
                baseline_option = next((o for o in base_options if o.get("level") == preferred), None)
                if not baseline_option and base_options: baseline_option = min(base_options, key=lambda o: amount(o["cost_excl_tax"]))
                baseline = amount(baseline_option["cost_excl_tax"]) if baseline_option else 0.0
                if complete:
                    rate_addr = lulu.address("Rate estimate", address.get("street1", ""), address.get("street2", ""),
                        address.get("city", ""), address.get("state", ""), country, address.get("postcode", ""), address.get("phone_number", ""))
                    async def cost(dest, ship_level):
                        return await lulu.request("POST", "/print-job-cost-calculations/", json={"line_items": lines, "shipping_address": dest, "shipping_option": ship_level})
                    calc = await cached(["lulu-cost", lines, rate_addr, level], lambda: cost(rate_addr, level))
                    actual = amount(calc.get("total_cost_incl_tax"))
                    if country == "US": baseline = actual
                    elif baseline_option:
                        base_rate_addr = {"name": "Rate estimate", "street1": "101 Independence Ave SE", "city": "Washington", "state_code": "DC", "postcode": "20540", "country_code": "US", "phone_number": os.getenv("LULU_MERCHANT_PHONE") or "+12025550100"}
                        calc_us = await cached(["lulu-cost-us", lines, baseline_option["level"]], lambda: cost(base_rate_addr, baseline_option["level"]))
                        baseline = amount(calc_us.get("total_cost_incl_tax"))
                else:
                    is_estimate = True
            except lulu.LuluError as exc:
                # Validation needs more address detail; it is not evidence of no delivery route.
                raise QuoteError("Please check the postal code, city and state/province (use its region code) to confirm delivery for this book.", status=422, reason="address_required", products=names) from None
            retail = surcharge(actual, baseline, country, True)
            leg = {"supplier": supplier, "from": "Print on demand", "logistic_name": "Lulu " + level,
                   "shipping_level": level, "shipping_total": retail,
                   "delivery_min": best.get("min_delivery_date"), "delivery_max": best.get("max_delivery_date")}
        else:
            raise QuoteError("This item is temporarily unavailable.", products=names)
        legs.append(leg)
        shipping_total += retail
    subtotal = round(sum(float(v.price_usd if v else p.price_usd) * q for p, v, q in cart), 2)
    shipping_total = round(shipping_total, 2)
    return {"available": True, "country_code": country, "product_total": subtotal, "shipping_total": shipping_total,
            "grand_total": round(subtotal + shipping_total, 2), "currency": "USD", "is_estimate": is_estimate,
            "logistic_name": " + ".join(str(l["logistic_name"]) for l in legs) or "Digital download",
            "eta_days": " / ".join(str(l["eta_days"]) for l in legs if l.get("eta_days")) or None,
            "digital_only": not groups, "has_digital": any(p.supplier == "digital" for p, _, _ in cart),
            "import_charges_notice": IMPORT_NOTE if groups else None, "legs": legs}
