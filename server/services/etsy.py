"""Etsy Open API v3 credentials for the supplier API pass-through.

ETSY_API_KEY is sent as x-api-key (keystring, or "keystring:shared_secret"
when Etsy asks for both); its keystring is the OAuth client_id. The OAuth
token lives in ETSY_TOKEN_FILE, created once by scripts/etsy_oauth.py and
refreshed here (Etsy rotates the refresh token on every refresh).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

BASE = "https://openapi.etsy.com/v3"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"


class EtsyError(RuntimeError):
    pass


def api_key() -> str:
    return (os.getenv("ETSY_API_KEY") or "").strip()


def client_id() -> str:
    return api_key().split(":")[0]


def token_file() -> Path:
    default = Path(__file__).resolve().parents[1] / "data" / "etsy_token.json"
    return Path(os.getenv("ETSY_TOKEN_FILE") or default)


def save_token(data: dict) -> None:
    token = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": int(time.time()) + int(data.get("expires_in", 3600)),
    }
    path = token_file()
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(token, f)
    os.replace(tmp, path)


async def access_token(client: httpx.AsyncClient) -> str:
    if not api_key():
        raise EtsyError("Etsy is not configured")
    try:
        token = json.loads(token_file().read_text())
    except (OSError, ValueError):
        raise EtsyError("Etsy is not connected; run scripts/etsy_oauth.py") from None
    if int(token.get("expires_at", 0)) - 60 > time.time():
        return token["access_token"]
    response = await client.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": client_id(),
        "refresh_token": token.get("refresh_token", ""),
    })
    if response.status_code != 200:
        raise EtsyError(f"Etsy token refresh failed: HTTP {response.status_code}")
    try:
        data = response.json()
        save_token(data)
    except (ValueError, KeyError, TypeError, OSError):
        raise EtsyError("Invalid Etsy token response or token file not writable") from None
    return data["access_token"]
