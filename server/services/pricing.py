"""
Retail price from CJ cost + payment fees + target margin.

Shipping is quoted separately at checkout (CJ freight × SHIPPING_MARKUP).
This module prices the product line only.

Formula (solve for list price P):

    net_after_paypal = P - (P * PAYPAL_PCT + PAYPAL_FIXED)
    net_after_cost   = net_after_paypal - cost - OPS_FIXED
    want: net_after_cost >= P * MARGIN_PCT   (margin as share of list price)

    => P - P*PAYPAL_PCT - PAYPAL_FIXED - cost - OPS_FIXED >= P * MARGIN_PCT
    => P * (1 - PAYPAL_PCT - MARGIN_PCT) >= cost + PAYPAL_FIXED + OPS_FIXED
    => P >= (cost + PAYPAL_FIXED + OPS_FIXED) / (1 - PAYPAL_PCT - MARGIN_PCT)

Then round up to a .99 psychological price (or .x9).
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class PriceBreakdown:
    cost_usd: float
    price_usd: float
    paypal_fee_usd: float
    ops_fixed_usd: float
    net_profit_usd: float
    margin_on_price: float
    markup_on_cost: float

    def as_dict(self) -> dict:
        return {
            "cost_usd": round(self.cost_usd, 2),
            "price_usd": round(self.price_usd, 2),
            "paypal_fee_usd": round(self.paypal_fee_usd, 2),
            "ops_fixed_usd": round(self.ops_fixed_usd, 2),
            "net_profit_usd": round(self.net_profit_usd, 2),
            "margin_on_price": round(self.margin_on_price, 4),
            "markup_on_cost": round(self.markup_on_cost, 2),
        }


def pricing_config() -> dict:
    return {
        # Target net margin as fraction of list price (after PayPal + cost + ops)
        "MARGIN_PCT": _f("PRICE_MARGIN_PCT", 0.40),
        # PayPal commercial (approx. US/Intl card); override in .env if needed
        "PAYPAL_PCT": _f("PAYPAL_FEE_PCT", 0.0349),
        "PAYPAL_FIXED": _f("PAYPAL_FEE_FIXED", 0.49),
        # Small per-item ops buffer (packaging time, returns, FX, CJ quirks)
        "OPS_FIXED": _f("PRICE_OPS_FIXED", 0.35),
        # Floor so tiny CJ items are not sold too cheap to look “cheap brand”
        "MIN_PRICE": _f("PRICE_MIN_USD", 6.99),
        # Legacy fallback multiplier if denominator invalid
        "MARKUP_MULTIPLIER": _f("MARKUP_MULTIPLIER", 2.4),
    }


def round_price_psych(amount: float) -> float:
    """Round up to x.99 (or keep if already .99-ish)."""
    if amount <= 0:
        return 0.0
    # ceil to next cent then force .99 of that dollar band
    dollars = math.floor(amount)
    candidate = dollars + 0.99
    if candidate + 1e-9 < amount:
        candidate = dollars + 1.99
    return round(candidate, 2)


def retail_from_cost(cost_usd: float) -> float:
    """Compute list price from unit CJ cost."""
    cfg = pricing_config()
    cost = max(0.0, float(cost_usd or 0))
    denom = 1.0 - cfg["PAYPAL_PCT"] - cfg["MARGIN_PCT"]
    if denom <= 0.05:
        # misconfigured env — safe fallback
        raw = cost * cfg["MARKUP_MULTIPLIER"] + cfg["PAYPAL_FIXED"] + cfg["OPS_FIXED"]
    else:
        raw = (cost + cfg["PAYPAL_FIXED"] + cfg["OPS_FIXED"]) / denom
    price = max(cfg["MIN_PRICE"], round_price_psych(raw))
    return price


def breakdown(cost_usd: float, price_usd: float | None = None) -> PriceBreakdown:
    cfg = pricing_config()
    cost = max(0.0, float(cost_usd or 0))
    price = float(price_usd) if price_usd is not None else retail_from_cost(cost)
    paypal = price * cfg["PAYPAL_PCT"] + cfg["PAYPAL_FIXED"]
    ops = cfg["OPS_FIXED"]
    net = price - paypal - cost - ops
    margin = (net / price) if price > 0 else 0.0
    markup = (price / cost) if cost > 0 else 0.0
    return PriceBreakdown(
        cost_usd=cost,
        price_usd=price,
        paypal_fee_usd=paypal,
        ops_fixed_usd=ops,
        net_profit_usd=net,
        margin_on_price=margin,
        markup_on_cost=markup,
    )
