"""Bonanza orders through the MathRelaxing gateway (local Unix socket, see /opt/mathrelaxing-bridge).

The gateway holds the Bonanza credentials and only allows a fixed list of calls; this module
never sees a token. Reads go straight through; writes carry an idempotency key, so the
gateway runs each write once even if it is sent twice.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
from typing import Any


class BonanzaError(RuntimeError):
    pass


def socket_path() -> str:
    return (os.getenv("BONANZA_GATEWAY_SOCKET") or "/run/mathrelaxing-bonanza-api/api.sock").strip()


def _call_sync(endpoint: str, payload: dict | None, key: str) -> dict:
    message: dict[str, Any] = {"action": "request", "method": "POST", "endpoint": endpoint, "payload": payload or {}}
    if key:
        message["idempotency_key"] = key
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(90)
            conn.connect(socket_path())
            conn.sendall(json.dumps(message).encode() + b"\n")
            with conn.makefile("rb") as stream:
                raw = stream.readline(8 * 1024 * 1024 + 1)
    except OSError as exc:
        raise BonanzaError(f"Bonanza gateway unavailable: {type(exc).__name__}") from None
    try:
        result = json.loads(raw)
    except ValueError:
        raise BonanzaError("Bonanza gateway sent an invalid reply") from None
    if result.get("status") != 200:
        raise BonanzaError(f"{endpoint[1:]}: {result.get('status')} {json.dumps(result.get('data'))[:300]}")
    return result.get("data") or {}


async def call(endpoint: str, payload: dict | None = None, key: str = "") -> dict:
    return await asyncio.to_thread(_call_sync, endpoint, payload, key)


def _unwrap(value: Any, name: str) -> Any:
    """Bonanza wraps list members ({"order": {...}}, {"item": {...}}); accept both shapes."""
    return value.get(name, value) if isinstance(value, dict) else value


def orders(data: dict) -> list[dict]:
    """The orders of a getOrdersResponse, each as a flat dict."""
    body = data.get("getOrdersResponse", data) if isinstance(data, dict) else {}
    raw = body.get("orderArray") or body.get("orders") or []
    return [_unwrap(o, "order") for o in raw if isinstance(_unwrap(o, "order"), dict)]


def order_id(order: dict) -> str:
    return str(order.get("orderID") or order.get("orderId") or order.get("id") or "").strip()


def is_paid(order: dict) -> bool:
    status = str(order.get("orderStatus") or "").lower()
    checkout = str((order.get("checkoutStatus") or {}).get("status") or "").lower()
    return bool(order.get("paidTime")) or status in {"completed", "invoiced"} or checkout == "complete"


def is_shipped(order: dict) -> bool:
    return bool(order.get("shippedTime")) or str(order.get("orderStatus") or "").lower() in {"shipped", "cancelled", "canceled"}


def items(order: dict) -> list[dict]:
    """[{sku, quantity, title, attributes: {name: value}}] for each line."""
    out = []
    for entry in order.get("itemArray") or order.get("items") or []:
        item = _unwrap(entry, "item")
        if not isinstance(item, dict):
            continue
        attrs = {}
        variation = item.get("variation") or item.get("variationSpecifics") or {}
        pairs = variation.get("nameValueList") if isinstance(variation, dict) else variation
        for pair in pairs or item.get("nameValueList") or []:
            if isinstance(pair, dict) and pair.get("name"):
                attrs[str(pair["name"]).strip()] = str(pair.get("value") or "").strip()
        try:
            qty = int(item.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 0
        out.append({"sku": str(item.get("sku") or item.get("SKU") or "").strip(), "quantity": qty,
                    "title": str(item.get("title") or "")[:120], "attributes": attrs})
    return out


def address(order: dict) -> dict:
    a = order.get("shippingAddress") or {}
    return {
        "name": str(a.get("name") or "").strip(),
        "line1": str(a.get("street1") or "").strip(),
        "line2": str(a.get("street2") or "").strip(),
        "city": str(a.get("cityName") or a.get("city") or "").strip(),
        "state": str(a.get("stateOrProvince") or a.get("state") or "").strip(),
        "zip": str(a.get("postalCode") or a.get("zip") or "").strip(),
        "country": str(a.get("country") or "").strip().upper(),
    }


def shape(order: dict) -> dict:
    """Keys only, for logs: never prints the buyer's name or address."""
    def keys(v):
        if isinstance(v, dict):
            return {k: keys(x) for k, x in v.items()}
        if isinstance(v, list):
            return [keys(v[0])] if v else []
        return type(v).__name__
    return keys(order)
