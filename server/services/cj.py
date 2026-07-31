"""
CJ Dropshipping API client (api2.0).

Local docs:  server/docs/cj-api/README.md
Official:    https://developers.cjdropshipping.com/
Auth header: CJ-Access-Token
Base:        https://developers.cjdropshipping.com/api2.0/v1
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


def is_configured() -> bool:
    return bool(os.getenv("CJ_API_KEY", "").strip())


async def get_access_token(force: bool = False) -> str:
    """POST /authentication/getAccessToken (or refresh)."""
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

    # code 0 is used by some video endpoints
    code = data.get("code")
    if code not in (200, 0, None) and not data.get("success"):
        if code != 200:
            raise CJError(data.get("message") or "CJ API error", data)
    return data.get("data")


async def get_product_details(
    *,
    pid: str | None = None,
    product_sku: str | None = None,
    variant_sku: str | None = None,
    features: list[str] | None = None,
    country_code: str | None = None,
) -> dict:
    """
    GET /product/query

    features examples: ["enable_video", "enable_combine"]
    When enable_video is set, data.productVideo may list video ids.
    """
    params: dict[str, Any] = {}
    if pid:
        params["pid"] = pid
    elif product_sku:
        params["productSku"] = product_sku
    elif variant_sku:
        params["variantSku"] = variant_sku
    else:
        raise CJError("pid, product_sku or variant_sku required")
    if features:
        # CJ accepts features as repeated query params or comma form; send first + list
        params["features"] = features
    if country_code:
        params["countryCode"] = country_code.upper()
    data = await _request("GET", "/product/query", params=params)
    return data or {}


async def search_products(
    keyword: str,
    page: int = 1,
    size: int = 20,
    *,
    features: list[str] | None = None,
    **extra: Any,
) -> dict:
    """GET /product/listV2 — elasticsearch product search."""
    params: dict[str, Any] = {
        "keyWord": keyword,
        "page": page,
        "size": size,
    }
    if features:
        params["features"] = features
    params.update({k: v for k, v in extra.items() if v is not None})
    return (await _request("GET", "/product/listV2", params=params)) or {}


async def list_products(
    *,
    page_num: int = 1,
    page_size: int = 20,
    product_sku: str | None = None,
    pid: str | None = None,
    **extra: Any,
) -> dict:
    """GET /product/list — legacy list (max 200/page)."""
    params: dict[str, Any] = {"pageNum": page_num, "pageSize": page_size}
    if product_sku:
        params["productSku"] = product_sku
    if pid:
        params["pid"] = pid
    params.update({k: v for k, v in extra.items() if v is not None})
    return (await _request("GET", "/product/list", params=params)) or {}


async def get_categories() -> list:
    """GET /product/getCategory"""
    data = await _request("GET", "/product/getCategory")
    return data or []


async def query_videos_by_product_id(product_id: str) -> list[dict]:
    """
    POST /product/queryVideosByProductId
    Body: { "productId": "<pid>" }
    Returns list of video objects (videoNumber, videoUrl, coverURL, …).
    """
    data = await _request(
        "POST",
        "/product/queryVideosByProductId",
        json_body={"productId": str(product_id)},
    )
    return data or []


async def freight_calculate(
    *,
    start_country: str,
    end_country: str,
    products: list[dict],
    zip_code: str | None = None,
) -> list[dict]:
    """
    POST /logistic/freightCalculate

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
    POST /shopping/order/createOrderV2

    payType: 1=page pay, 2=balance, 3=create only (no charge).
    """
    data = await _request("POST", "/shopping/order/createOrderV2", json_body=payload)
    return data or {}
