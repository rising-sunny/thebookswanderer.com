"""Offline Qikink catalog planning. Never publishes products or submits orders.

Supplier quotes and FX rates are operator-supplied evidence, not Qikink API
responses. A Sandbox order's selling value is never treated as a supplier cost.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.qikink import PrintDesign

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "config/qikink_sandbox_catalog.json"
DEFAULT_STORE_DB = Path(__file__).resolve().parents[1] / "data/store.db"


class DraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Quote(DraftModel):
    """One explicitly itemized quote for ONE unit, SKU, destination and method."""
    sku: str = Field(min_length=1, max_length=50)
    design: PrintDesign
    quantity: Literal[1] = 1
    country: str = Field(pattern=r"^[A-Z]{2}$")
    postal_code: str = Field(min_length=1, max_length=20)
    method: str = Field(min_length=1, max_length=100)
    eta_min_days: int = Field(ge=1, le=365)
    eta_max_days: int = Field(ge=1, le=365)
    currency: Literal["INR"] = "INR"
    product: Decimal = Field(ge=0, allow_inf_nan=False)
    printing: Decimal = Field(ge=0, allow_inf_nan=False)
    packaging: Decimal = Field(ge=0, allow_inf_nan=False)
    tax: Decimal = Field(ge=0, allow_inf_nan=False)
    shipping: Decimal = Field(ge=0, allow_inf_nan=False)
    other: Decimal = Field(ge=0, allow_inf_nan=False)
    source: str = Field(min_length=1, max_length=300)
    confirmed_on: date
    valid_until: date

    @model_validator(mode="after")
    def consistent(self):
        if self.valid_until < self.confirmed_on or self.eta_max_days < self.eta_min_days:
            raise ValueError("Inconsistent quote dates or delivery range")
        if self.total() <= 0:
            raise ValueError("A zero total is not a confirmed supplier quote")
        return self

    def total(self) -> Decimal:
        return self.product + self.printing + self.packaging + self.tax + self.shipping + self.other


class FX(DraftModel):
    currency_pair: Literal["INR_USD"] = "INR_USD"
    usd_per_inr: Decimal = Field(gt=0, allow_inf_nan=False)
    source: str = Field(min_length=1, max_length=300)
    confirmed_on: date
    valid_until: date

    @model_validator(mode="after")
    def consistent(self):
        if self.valid_until < self.confirmed_on:
            raise ValueError("Inconsistent FX dates")
        return self


class DraftVariant(DraftModel):
    key: str = Field(pattern=r"^[a-z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=300)
    store_product_id: int | None = Field(default=None, gt=0)
    store_variant_id: int | None = Field(default=None, gt=0)
    sku: str = Field(min_length=1, max_length=50)
    design: PrintDesign
    mockup_is_placeholder: bool = True
    sandbox_order_id: str | None = Field(default=None, pattern=r"^[0-9]+$")
    sandbox_reference: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,15}$")
    cost_quotes: list[Quote] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self):
        if (self.store_product_id is None) != (self.store_variant_id is None):
            raise ValueError("Provide both store product and variant IDs, or neither")
        if any(q.sku != self.sku for q in self.cost_quotes):
            raise ValueError("Cost quote SKU does not match this variant")
        if any(q.design != self.design for q in self.cost_quotes):
            raise ValueError("Cost quote design does not match this variant")
        if bool(self.sandbox_order_id) != bool(self.sandbox_reference):
            raise ValueError("Provide both Sandbox reference and order ID")
        return self


class DraftCatalog(DraftModel):
    version: Literal[1] = 1
    environment: Literal["sandbox"] = "sandbox"
    requested_countries: list[str] = Field(default_factory=list)
    variants: list[DraftVariant]
    fx: FX | None = None

    @model_validator(mode="after")
    def consistent(self):
        if not self.variants or len({v.key for v in self.variants}) != len(self.variants):
            raise ValueError("Variant keys must be unique and the catalog non-empty")
        bindings = [(v.store_product_id, v.store_variant_id) for v in self.variants if v.store_product_id]
        if len(bindings) != len(set(bindings)):
            raise ValueError("Store variants cannot be mapped more than once")
        if len(set(self.requested_countries)) != len(self.requested_countries):
            raise ValueError("Duplicate destination country")
        if any(len(c) != 2 or not c.isascii() or not c.isupper() or not c.isalpha() for c in self.requested_countries):
            raise ValueError("Use uppercase two-letter country codes")
        return self


def load_catalog(path: Path = DEFAULT_CATALOG) -> DraftCatalog:
    return DraftCatalog.model_validate_json(Path(path).read_text())


def _mapping_blockers(variant: DraftVariant, store_db: Path) -> list[str]:
    if variant.store_product_id is None:
        return ["store_product_and_variant_not_selected"]
    # mode=ro is essential: never create a fresh empty store.db while checking.
    uri = Path(store_db).resolve().as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as db:
            row = db.execute("""SELECT p.id, v.product_id, p.active, v.active
                FROM products p JOIN product_variants v ON v.id=? WHERE p.id=?""",
                (variant.store_variant_id, variant.store_product_id)).fetchone()
    except sqlite3.Error:
        return ["store_mapping_unverified"]
    if row is None or row[0] != row[1]:
        return ["store_variant_does_not_belong_to_product"]
    if row[2] or row[3]:
        return ["linked_store_product_or_variant_is_active"]
    return []


def _current(confirmed: date, expires: date, today: date) -> bool:
    return confirmed <= today <= expires


def _retail_estimate(cost: Decimal, config: dict) -> Decimal:
    """All-in retail worksheet: shipping is included, not a checkout quote."""
    margin = Decimal(str(config["MARGIN_PCT"]))
    fee_pct = Decimal(str(config["PAYPAL_PCT"]))
    fixed = Decimal(str(config["PAYPAL_FIXED"]))
    ops = Decimal(str(config["OPS_FIXED"]))
    floor = Decimal(str(config["MIN_PRICE"]))
    if (not all(x.is_finite() for x in (margin, fee_pct, fixed, ops, floor))
            or margin < 0 or fee_pct < 0 or margin + fee_pct >= 1
            or min(fixed, ops, floor) < 0):
        raise ValueError("Invalid pricing assumptions")
    raw = max(floor, (cost + fixed + ops) / (1 - margin - fee_pct))
    # The smallest x.99 price that covers the calculated minimum.
    return (raw - Decimal("0.99")).to_integral_value(rounding=ROUND_CEILING) + Decimal("0.99")


def catalog_report(catalog: DraftCatalog, store_db: Path = DEFAULT_STORE_DB,
                   *, today: date | None = None, pricing: dict | None = None) -> dict:
    from services.pricing import pricing_config
    today = today or datetime.now(ZoneInfo("America/Santiago")).date()
    pricing = pricing_config() if pricing is None else pricing
    rows = []
    for variant in catalog.variants:
        blockers = _mapping_blockers(variant, store_db)
        if variant.mockup_is_placeholder:
            blockers.append("real_product_mockup_not_supplied")
        if not variant.sandbox_order_id:
            blockers.append("sandbox_creation_evidence_missing")
        if not catalog.requested_countries:
            blockers.append("sales_destinations_not_selected")
        destinations = []
        for country in catalog.requested_countries:
            quotes = [q for q in variant.cost_quotes if q.country == country and _current(q.confirmed_on, q.valid_until, today)]
            if not quotes:
                destinations.append({"country": country, "state": "quote_required", "retail_estimate_usd": None})
                continue
            for quote in quotes:
                result = {"country": country, "postal_code": quote.postal_code,
                          "method": quote.method, "quantity": 1,
                          "state": "fx_required", "retail_estimate_usd": None,
                          "all_in_cost_inr": str(quote.total()),
                          "quote_source": quote.source, "valid_until": quote.valid_until.isoformat()}
                if catalog.fx and _current(catalog.fx.confirmed_on, catalog.fx.valid_until, today):
                    # Keep full precision until the final displayed USD amount.
                    usd = quote.total() * catalog.fx.usd_per_inr
                    try:
                        estimate = _retail_estimate(usd, pricing)
                    except (ValueError, ArithmeticError):
                        result["state"] = "pricing_configuration_invalid"
                    else:
                        result.update(state="worksheet_only", all_in_cost_usd=str(usd),
                                      retail_estimate_usd=f"{estimate:.2f}",
                                      fx_source=catalog.fx.source,
                                      eta_days=[quote.eta_min_days, quote.eta_max_days])
                destinations.append(result)
        rows.append({"key": variant.key, "sku": variant.sku,
                     "store_product_id": variant.store_product_id,
                     "store_variant_id": variant.store_variant_id,
                     "sandbox_order_id": variant.sandbox_order_id,
                     "sandbox_reference": variant.sandbox_reference,
                     "blockers": blockers, "destinations": destinations})
    return {"environment": "sandbox", "as_of": today.isoformat(), "public_sales_enabled": False,
            "integration_state": "draft_only",
            "note": "No live API or checkout integration. Quotes apply only to their listed postal code and one unit; they do not establish country-wide shipping coverage.",
            "variants": rows}
