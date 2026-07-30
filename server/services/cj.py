"""
CJ Dropshipping API client (api2.0).

Docs: https://developers.cjdropshipping.com/
Auth header: CJ-Access-Token
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

BASE = "https://developers.cjdropshipping.com/api2.0/v1"

_token: str | None = None
_token_expiry_ts: float = 0.0
_refresh_token: str | None = None


class CJError(RuntimeError):
    def __init__(self, message: str, payload: Any = None):
        super().__init__(message)
        self.payload = payload


def _api_key() -> str:
    key = os.getenv("CJ_API_KEY", "").strip()
    if not key:
        raise CJError("CJ_API_KEY is not configured")
    return key


async def get_access_token(force: bool = False) -> str:
    global _token, _token_expiry_ts, _refresh_token

    now = time.time()
    if not force and _token and now < _token_expiry_ts - 60:
        return _token

    # Prefer refresh if we still have one
    if not force and _refresh_token:
        try:
            return await _refresh_access_token()
        except CJError:
            pass

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE}/authentication/getAccessToken",
            json={"apiKey": _api_key()},
        )
        data = resp.json()

    if not data.get("success") and data.get("code") != 200:
        raise CJError(data.get("message") or "getAccessToken failed", data)

    result = data.get("data") or {}
    _token = result.get("accessToken")
    _refresh_token = result.get("refreshToken")
    # Conservative cache: 12h (API says ~15 days for access token)
    _token_expiry_ts = now + 12 * 3600
    if not _token:
        raise CJError("No accessToken in CJ response", data)
    return _token


async def _refresh_access_token() -> str:
    global _token, _token_expiry_ts, _refresh_token
    if not _refresh_token:
        raise CJError("No refresh token")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE}/authentication/refreshAccessToken",
            json={"refreshToken": _refresh_token},
        )
        data = resp.json()

    if not data.get("success") and data.get("code") != 200:
        raise CJError(data.get("message") or "refreshAccessToken failed", data)

    result = data.get("data") or {}
    _token = result.get("accessToken")
    if result.get("refreshToken"):
        _refresh_token = result["refreshToken"]
    _token_expiry_ts = time.time() + 12 * 3600
    if not _token:
        raise CJError("No accessToken after refresh", data)
    return _token


async def _request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | list | None = None,
) -> Any:
    token = await get_access_token()
    headers = {"CJ-Access-Token": token, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.request(
            method,
            f"{BASE}{path}",
            headers=headers,
            params=params,
            json=json_body,
        )
        # Retry once on auth failure
        if resp.status_code in (401, 403):
            token = await get_access_token(force=True)
            headers["CJ-Access-Token"] = token
            resp = await client.request(
                method,
                f"{BASE}{path}",
                headers=headers,
                params=params,
                json=json_body,
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise CJError(f"Invalid JSON from CJ ({resp.status_code})", resp.text) from exc

    if data.get("code") not in (200, None) and not data.get("success"):
        # Some endpoints only set code=200
        if data.get("code") != 200:
            raise CJError(data.get("message") or "CJ API error", data)
    return data.get("data")


async def get_product_details(
    *,
    pid: str | None = None,
    product_sku: str | None = None,
    variant_sku: str | None = None,
) -> dict:
    params: dict[str, str] = {}
    if pid:
        params["pid"] = pid
    elif product_sku:
        params["productSku"] = product_sku
    elif variant_sku:
        params["variantSku"] = variant_sku
    else:
        raise CJError("pid, product_sku or variant_sku required")
    data = await _request("GET", "/product/query", params=params)
    return data or {}


async def search_products(keyword: str, page: int = 1, size: int = 20) -> dict:
    return (
        await _request(
            "GET",
            "/product/listV2",
            params={"keyWord": keyword, "page": page, "size": size},
        )
        or {}
    )


async def freight_calculate(
    *,
    start_country: str,
    end_country: str,
    products: list[dict],
    zip_code: str | None = None,
) -> list[dict]:
    """
    products: [{ "vid": "...", "quantity": 1 }, ...]
    Returns list of logistics options with price + aging.
    """
    body: dict[str, Any] = {
        "startCountryCode": start_country,
        "endCountryCode": end_country,
        "products": products,
    }
    if zip_code:
        body["zip"] = zip_code
    data = await _request("POST", "/logistic/freightCalculate", json_body=body)
    return data or []


async def create_order(payload: dict) -> dict:
    """
    Create order on CJ (createOrderV2).
    payType: 1=page pay, 2=balance, 3=create only (no charge).
    """
    data = await _request("POST", "/shopping/order/createOrderV2", json_body=payload)
    return data or {}
