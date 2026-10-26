"""Pass-through to supplier APIs for the restricted admin API.

The store keeps the keys. main.py lets reads straight through and asks for a
preview code before any write. Orders and payments stay blocked unless
TBW_SUPPLIER_ORDERS_ENABLED=1 is set on the VPS. Responses lose customer
personal data and are truncated.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from fastapi import HTTPException

from services import cj, etsy, lulu, pinterest, printify, prodigi_store, slant3d

SUPPLIERS = ("cj", "printify", "lulu", "prodigi", "slant3d", "etsy", "meta", "pinterest")
META_GRAPH = "https://graph.facebook.com/v21.0"
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
LIMIT = 60_000

_PATH = re.compile(r"/[A-Za-z0-9._~/-]{0,300}(\?[A-Za-z0-9._~=&%,+:-]{0,500})?")
# Paths that create orders, touch sales or spend money: CJ shopping/pay,
# Printify orders, Lulu print jobs, Prodigi and Slant 3D orders, Etsy receipts, and Meta
# or Pinterest ads.
_MONEY = re.compile(
    r"order|pay|wallet|balance|checkout|print-jobs|send_to_production|receipts|transactions"
    r"|/act_|ad_?accounts|adsets|adcreatives|campaigns|/ads(/|$|\?)",
    re.I,
)
_PRIVATE = re.compile(
    r"(e_?mail\w*|phone\w*|tel|mobile|address\w*|street\w*|zip\w*|post_?code|postal_?code"
    r"|(first|last|full|given|family)_?name|recipient\w*|customer\w*|consignee\w*|buyer\w*"
    r"|\w*token|\w*secret|password|api_?key)",
    re.I,
)


class SupplierAPIError(Exception):
    pass


def orders_enabled() -> bool:
    return os.getenv("TBW_SUPPLIER_ORDERS_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def check(supplier: str, method: str, path: str) -> None:
    """ValueError for a malformed call, PermissionError for a blocked one."""
    if supplier not in SUPPLIERS:
        raise ValueError("Unknown supplier")
    if method not in METHODS:
        raise ValueError("Unsupported method")
    if not _PATH.fullmatch(path) or ".." in path or "//" in path:
        raise ValueError("Invalid path")
    if method != "GET" and _MONEY.search(path.split("?")[0]) and not orders_enabled():
        raise PermissionError("Orders and payments are disabled")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[redacted]" if _PRIVATE.fullmatch(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


async def _send(client: httpx.AsyncClient, supplier: str, method: str, path: str, body: Any):
    if supplier == "printify":
        if not printify.configured():
            raise SupplierAPIError("Printify is not configured")
        url = printify.BASE + path
        headers = {"Authorization": f"Bearer {printify._token()}", "User-Agent": "TheBooksWanderer"}
    elif supplier == "lulu":
        if not lulu.configured():
            raise SupplierAPIError("Lulu is not configured")
        url = lulu.base() + path
        headers = {"Authorization": "Bearer " + await lulu._token(client)}
    elif supplier == "prodigi":
        url = prodigi_store.BASE + path
        headers = {"X-API-Key": prodigi_store.key()}
    elif supplier == "slant3d":
        url = slant3d.BASE + path
        headers = slant3d.headers()
    elif supplier == "etsy":
        url = etsy.BASE + path
        headers = {"x-api-key": etsy.api_key(), "Authorization": "Bearer " + await etsy.access_token(client)}
    elif supplier == "meta":
        token = (os.getenv("FB_PAGE_TOKEN") or "").strip()
        if not token:
            raise SupplierAPIError("Meta is not configured")
        url = META_GRAPH + path
        headers = {"Authorization": "Bearer " + token}
    elif supplier == "pinterest":
        url = pinterest.api_base() + path
        headers = {"Authorization": "Bearer " + await pinterest.access_token()}
    else:
        url = cj.BASE + path
        headers = {"CJ-Access-Token": await cj.get_access_token()}
    return await client.request(method, url, headers=headers, json=body)


async def call(supplier: str, method: str, path: str, body: Any = None) -> dict[str, Any]:
    check(supplier, method, path)
    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
            response = await _send(client, supplier, method, path, body)
    except httpx.HTTPError:
        raise SupplierAPIError(f"{supplier} unavailable") from None
    except (cj.CJError, lulu.LuluError, prodigi_store.ProdigiError, slant3d.Slant3DError, etsy.EtsyError,
            HTTPException):
        raise SupplierAPIError(f"{supplier} authentication failed or not connected") from None
    try:
        data = redact(response.json())
    except ValueError:
        data = response.text[:2000]
    text = json.dumps(data, ensure_ascii=False)
    truncated = len(text) > LIMIT
    return {"status": response.status_code, "data": text[:LIMIT] if truncated else data,
            "truncated": truncated}
