"""
Lulu Print API client (print-on-demand books and booklets).

Env:
  LULU_CLIENT_KEY / LULU_CLIENT_SECRET   API keys (developers.lulu.com > API Keys)
  LULU_ENV                               "production" (default) or "sandbox"
Docs: https://api.lulu.com/docs/
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

_TOKEN: dict[str, Any] = {}


class LuluError(RuntimeError):
    def __init__(self, message: str, payload: Any = None):
        super().__init__(message)
        self.payload = payload


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def base() -> str:
    return "https://api.sandbox.lulu.com" if _env("LULU_ENV") == "sandbox" else "https://api.lulu.com"


def configured() -> bool:
    return bool(_env("LULU_CLIENT_KEY") and _env("LULU_CLIENT_SECRET"))


async def _token(client: httpx.AsyncClient) -> str:
    if _TOKEN.get("value") and _TOKEN.get("expires", 0) > time.time() + 60:
        return _TOKEN["value"]
    r = await client.post(
        f"{base()}/auth/realms/glasstree/protocol/openid-connect/token",
        auth=(_env("LULU_CLIENT_KEY"), _env("LULU_CLIENT_SECRET")),
        data={"grant_type": "client_credentials"},
    )
    if r.status_code != 200:
        raise LuluError(f"auth failed: HTTP {r.status_code}", r.text[:300])
    data = r.json()
    _TOKEN.update(value=data["access_token"], expires=time.time() + int(data.get("expires_in", 300)))
    return _TOKEN["value"]


async def request(method: str, path: str, json: Any = None) -> Any:
    if not configured():
        raise LuluError("LULU_CLIENT_KEY / LULU_CLIENT_SECRET not set")
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _token(client)
        r = await client.request(
            method, f"{base()}{path}", json=json, headers={"Authorization": f"Bearer {token}"}
        )
    if r.status_code >= 400:
        try:
            payload = r.json()
        except ValueError:
            payload = r.text[:500]
        raise LuluError(f"{method} {path}: HTTP {r.status_code}", payload)
    return r.json() if r.content else None


async def cost(pod_package_id: str, page_count: int, quantity: int, address: dict[str, str],
               shipping_option: str = "MAIL") -> dict[str, Any]:
    """Print + shipping cost for one line item (no order is created)."""
    return await request("POST", "/print-job-cost-calculations/", {
        "line_items": [{"pod_package_id": pod_package_id, "page_count": page_count, "quantity": quantity}],
        "shipping_address": address,
        "shipping_option": shipping_option,
    })
