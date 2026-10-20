"""Prodigi Live product details and US/USD quotes only; no order transport."""
import os
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt

BASE = "https://api.prodigi.com/v4.0"
SKU_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}"


class ProdigiError(RuntimeError):
    """Safe message only: never includes credentials or upstream bodies."""


class QuoteAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    printArea: str = Field(min_length=1, max_length=100)
    pageCount: StrictInt | None = Field(default=None, ge=1, le=10000)


class QuoteItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    sku: str = Field(pattern="^" + SKU_PATTERN + "$", max_length=200)
    copies: StrictInt = Field(default=1, ge=1, le=100)
    attributes: dict[str, str] = Field(default_factory=dict, max_length=20)
    assets: list[QuoteAsset] = Field(min_length=1, max_length=20)


class Client:
    def __init__(self, key, *, transport=None):
        if not isinstance(key, str) or not key.strip():
            raise ProdigiError("PRODIGI_API_KEY is not configured")
        self._key = key.strip()
        self._http = httpx.AsyncClient(
            timeout=30, follow_redirects=False, transport=transport
        )

    @classmethod
    def from_env(cls):
        return cls(os.getenv("PRODIGI_API_KEY", ""))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._http.aclose()

    async def _request(self, method, path, payload=None):
        # Check before any authenticated request. No arbitrary hosts or order paths.
        product_read = method == "GET" and re.fullmatch(
            r"/products/" + SKU_PATTERN, path
        )
        quote_only = method == "POST" and path == "/quotes"
        if not (product_read or quote_only):
            raise ProdigiError("Prodigi operation is disabled")
        try:
            response = await self._http.request(
                method, BASE + path,
                headers={"X-API-Key": self._key}, json=payload,
            )
            if response.status_code != 200:
                raise ProdigiError(f"Prodigi request failed: HTTP {response.status_code}")
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise ProdigiError("Prodigi unavailable or invalid response") from None
        if not isinstance(data, dict):
            raise ProdigiError("Invalid Prodigi response")
        outcome = str(data.get("outcome", "")).lower()
        if product_read:
            product = data.get("product")
            if (outcome != "ok" or not isinstance(product, dict)
                or str(product.get("sku", "")).casefold() != path[10:].casefold()
                or not isinstance(product.get("variants"), list)):
                raise ProdigiError("Invalid Prodigi product response")
        elif (outcome not in {"created", "createdwithissues"}
              or not isinstance(data.get("quotes"), list) or not data["quotes"]
              or any(not isinstance(q, dict) or not isinstance(q.get("costSummary"), dict)
                     for q in data["quotes"])):
            raise ProdigiError("Invalid Prodigi quote response")
        return data

    async def product_details(self, sku):
        if not isinstance(sku, str) or re.fullmatch(SKU_PATTERN, sku) is None:
            raise ProdigiError("Invalid Prodigi SKU")
        return await self._request("GET", "/products/" + sku)

    async def quote_us(self, items):
        # Typed input excludes addresses, artwork URLs and order-creation fields.
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise ProdigiError("Quote requires between 1 and 20 items")
        try:
            normalized = [QuoteItem.model_validate(i) for i in items]
        except ValueError:
            raise ProdigiError("Invalid Prodigi quote items") from None
        return await self._request("POST", "/quotes", {
            "destinationCountryCode": "US", "currencyCode": "USD",
            "items": [i.model_dump(exclude_none=True) for i in normalized],
        })

    async def create_order(self, *args, **kwargs):
        raise ProdigiError("Prodigi order submission is disabled")
