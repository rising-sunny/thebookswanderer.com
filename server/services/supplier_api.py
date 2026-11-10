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
from pathlib import Path
from typing import Any

import httpx

from fastapi import HTTPException

from services import cj, etsy, lulu, pinterest, printify, prodigi_store, slant3d

SUPPLIERS = ("cj", "printify", "lulu", "prodigi", "slant3d", "etsy", "meta", "pinterest", "alura")
META_GRAPH = "https://graph.facebook.com/v21.0"
# Alura (Etsy market research) is read-only here and bills API credits per call. The key lives only
# in this server's environment (ALURA_API_KEY) and is never returned.
ALURA_BASE = "https://api.alura.io/v1"
_ALURA_PATH = re.compile(r"/(me|me/workspaces|usage|usage/by-day|usage/events|languages|categories(/[0-9]{1,12})?"
                         r"|research(/[A-Za-z0-9_-]{1,80}){1,6})")
_ALURA_FREE = re.compile(r"/(me|me/workspaces|usage|usage/by-day|usage/events|languages|categories(/[0-9]{1,12})?)")
_alura_remaining: int | None = None  # last "Alura-Credits-Remaining" seen
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
    r"(e_?mail\w*|phone\w*|tel|mobile|\w*address\w*|street\w*|zip\w*|post_?code|postal_?code"
    r"|(first|second|third)_?line|line_?[123]"
    r"|(first|last|full|given|family)_?name|recipient\w*|customer\w*|consignee\w*|buyer\w*"
    r"|\w*token|\w*secret|password|api_?key)",
    re.I,
)


# Meta video upload from a file already on this server (JSON bodies cannot carry binary data and
# Meta's own download of a file_url has failed with an unspecific error). The body names the file
# with "local_file", relative to the site's assets folder; it is sent as a multipart "source".
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
VIDEO_SUFFIXES = {".mp4", ".mov"}
MAX_VIDEO_BYTES = 100 * 1024 * 1024
_META_VIDEO_PATH = re.compile(r"/act_\d{1,25}/advideos")
_ETSY_VIDEO_PATH = re.compile(r"/application/shops/\d{1,15}/listings/\d{1,15}/videos")
_VIDEO_PATHS = {"meta": _META_VIDEO_PATH, "etsy": _ETSY_VIDEO_PATH}


def meta_local_video(body: Any) -> Path | None:
    """The file named by body["local_file"], or None when the body has none. ValueError if unusable."""
    if not isinstance(body, dict) or "local_file" not in body:
        return None
    name = body["local_file"]
    if not isinstance(name, str) or not name or name.startswith("/") or ".." in name.split("/"):
        raise ValueError("local_file must be a path inside the assets folder")
    if "file_url" in body or "source" in body:
        raise ValueError("local_file cannot be combined with file_url or source")
    root = ASSETS_DIR.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in VIDEO_SUFFIXES or not path.is_file():
        raise ValueError("local_file must be an existing .mp4 or .mov inside the assets folder")
    if path.stat().st_size > MAX_VIDEO_BYTES:
        raise ValueError("local_file is larger than the 100 MB limit")
    return path


def _form_fields(body: dict) -> dict[str, str]:
    out = {}
    for key, value in body.items():
        if key == "local_file":
            continue
        out[key] = json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
    return out


class SupplierAPIError(Exception):
    pass


def orders_enabled() -> bool:
    return os.getenv("TBW_SUPPLIER_ORDERS_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def check(supplier: str, method: str, path: str, body: Any = None) -> None:
    """ValueError for a malformed call, PermissionError for a blocked one."""
    if supplier not in SUPPLIERS:
        raise ValueError("Unknown supplier")
    if method not in METHODS:
        raise ValueError("Unsupported method")
    if not _PATH.fullmatch(path) or ".." in path or "//" in path:
        raise ValueError("Invalid path")
    if supplier == "alura":
        base = path.split("?")[0]
        if method != "GET":
            raise PermissionError("Alura is read-only here")
        if not _ALURA_PATH.fullmatch(base):
            raise ValueError("That Alura path is not available here")
        reserve = int(os.getenv("ALURA_MIN_CREDITS_RESERVE", "10") or 10)
        if not _ALURA_FREE.fullmatch(base) and _alura_remaining is not None and _alura_remaining < reserve:
            raise PermissionError("Alura credits are almost used up; check /usage before more research")
    if supplier in _VIDEO_PATHS and method != "GET" and isinstance(body, dict) and "local_file" in body:
        if method != "POST" or not _VIDEO_PATHS[supplier].fullmatch(path.split("?")[0]):
            raise ValueError("local_file is only for POST /act_<id>/advideos (Meta) "
                             "or POST /application/shops/<id>/listings/<id>/videos (Etsy)")
        meta_local_video(body)
    if supplier == "meta" and method != "GET" and not orders_enabled():
        _check_meta_ad_write(method, path, body)
        if _META_AD_PATH.fullmatch(path.split("?")[0]):
            return
    if method != "GET" and _MONEY.search(path.split("?")[0]) and not orders_enabled() \
            and not _unpaid_draft(supplier, method, path):
        raise PermissionError("Orders and payments are disabled")


# Meta ads can be built while orders stay disabled, but only paused: campaigns, ad sets and ads
# are created with status PAUSED, nothing is ever switched to ACTIVE through this route (the
# owner activates in Ads Manager), and a daily budget may not exceed
# TBW_META_ADS_MAX_DAILY_BUDGET (account currency, minor units; unset = Meta ads stay blocked).
_META_AD_PATH = re.compile(r"/act_\d{1,25}/(campaigns|adsets|ads|adcreatives|adimages|advideos)|/\d{1,25}")
_META_NEEDS_PAUSED = re.compile(r"/act_\d{1,25}/(campaigns|adsets|ads)")
_META_STATUS_KEYS = {"status", "configured_status", "effective_status"}
_META_SAFE_STATUS = {"PAUSED", "ARCHIVED", "DELETED"}
_META_BLOCKED_KEYS = {"lifetime_budget", "spend_cap", "spend_cap_action"}


def meta_ads_max_daily_budget() -> int:
    try:
        return max(0, int(os.getenv("TBW_META_ADS_MAX_DAILY_BUDGET", "0").strip() or 0))
    except ValueError:
        return 0


def _walk(value: Any):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)


def _check_meta_ad_write(method: str, path: str, body: Any) -> None:
    base = path.split("?")[0]
    for key, value in _walk(body):
        if key in _META_STATUS_KEYS and str(value).upper() not in _META_SAFE_STATUS:
            raise PermissionError("Meta objects can only be paused, archived or deleted here; activate in Ads Manager")
    if not _META_AD_PATH.fullmatch(base):
        return
    limit = meta_ads_max_daily_budget()
    if not limit or method != "POST" or not isinstance(body, dict):
        raise PermissionError("Meta ads are disabled")
    if _META_NEEDS_PAUSED.fullmatch(base) and str(body.get("status", "")).upper() != "PAUSED":
        raise PermissionError("New Meta campaigns, ad sets and ads must be created with status PAUSED")
    for key, value in _walk(body):
        if key in _META_BLOCKED_KEYS:
            raise PermissionError(f"{key} is not allowed here; use a daily budget")
        if key == "daily_budget":
            try:
                amount = int(str(value))
            except ValueError:
                raise PermissionError("daily_budget must be a whole number") from None
            if amount > limit:
                raise PermissionError(f"daily_budget above the limit of {limit}")


def _unpaid_draft(supplier: str, method: str, path: str) -> bool:
    """A Slant 3D draft order only prices print and shipping; the charge comes
    with POST /orders/{id}, which stays blocked."""
    return supplier == "slant3d" and method == "POST" and path.split("?")[0] == "/orders"


# A dict that holds a postal address (an Etsy receipt, a Lulu shipping_address) also names
# the person and the city in plain keys; "name" alone stays visible elsewhere (options, boards).
_ADDRESS_HINT = re.compile(r"(\w*address\w*|street\w*|(first|second)_?line|line_?1|post_?code|postal_?code|zip\w*)", re.I)
_PRIVATE_IN_ADDRESS = re.compile(r"(name|city|town|organization|company)", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        postal = any(_ADDRESS_HINT.fullmatch(str(k)) for k in value)
        return {
            k: "[redacted]" if _PRIVATE.fullmatch(str(k)) or (postal and _PRIVATE_IN_ADDRESS.fullmatch(str(k)))
            else redact(v)
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
        video = meta_local_video(body)
        if video is not None:
            return await client.post(url, headers=headers, data=_form_fields(body),
                                     files={"video": (video.name, video.read_bytes(), "video/mp4")})
    elif supplier == "meta":
        token = (os.getenv("FB_PAGE_TOKEN") or "").strip()
        if not token:
            raise SupplierAPIError("Meta is not configured")
        url = META_GRAPH + path
        headers = {"Authorization": "Bearer " + token}
        video = meta_local_video(body)
        if video is not None:
            return await client.post(url, headers=headers, data=_form_fields(body),
                                     files={"source": (video.name, video.read_bytes(), "video/mp4")})
    elif supplier == "alura":
        key = (os.getenv("ALURA_API_KEY") or "").strip()
        if not key:
            raise SupplierAPIError("Alura is not configured")
        url = ALURA_BASE + path
        headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    elif supplier == "pinterest":
        url = pinterest.api_base() + path
        headers = {"Authorization": "Bearer " + await pinterest.access_token()}
    else:
        url = cj.BASE + path
        headers = {"CJ-Access-Token": await cj.get_access_token()}
    return await client.request(method, url, headers=headers, json=body)


async def call(supplier: str, method: str, path: str, body: Any = None) -> dict[str, Any]:
    check(supplier, method, path, body)
    try:
        slow = supplier in _VIDEO_PATHS and isinstance(body, dict) and "local_file" in body
        async with httpx.AsyncClient(timeout=300 if slow else 45, follow_redirects=False) as client:
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
    result = {"status": response.status_code, "data": text[:LIMIT] if truncated else data,
              "truncated": truncated}
    if supplier == "alura":
        global _alura_remaining
        cost, left = response.headers.get("Alura-Credits-Cost"), response.headers.get("Alura-Credits-Remaining")
        if left is not None and left.strip().isdigit():
            _alura_remaining = int(left)
        result["credits"] = {"cost": cost, "remaining": left}
    return result
