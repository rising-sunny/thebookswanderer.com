"""Pinterest API v5 client for The Books Wanderer (own app + OAuth token)."""
from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

DEFAULT_API_BASE = "https://api.pinterest.com/v5"
OAUTH_AUTHORIZE_URL = "https://www.pinterest.com/oauth/"
DEFAULT_SCOPES = (
    "boards:read,boards:write,pins:read,pins:write,"
    "user_accounts:read,user_accounts:write"
)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def public_base() -> str:
    return _env("PUBLIC_BASE_URL", "https://thebookswanderer.com").rstrip("/")


def api_base() -> str:
    return _env("PINTEREST_API_BASE", DEFAULT_API_BASE).rstrip("/")


def client_id() -> str:
    return _env("PINTEREST_CLIENT_ID")


def client_secret() -> str:
    return _env("PINTEREST_CLIENT_SECRET")


def redirect_uri() -> str:
    return _env(
        "PINTEREST_REDIRECT_URI",
        f"{public_base()}/api/pinterest/oauth/callback",
    )


def scopes() -> str:
    return _env("PINTEREST_SCOPES", DEFAULT_SCOPES)


def scope_list() -> list[str]:
    return [s for s in scopes().replace(" ", ",").split(",") if s]


def token_path() -> Path:
    raw = _env("PINTEREST_TOKEN_FILE")
    if raw:
        return Path(raw)
    # Prefer server/data next to the DB (writable on VPS, gitignored).
    return Path(__file__).resolve().parent.parent / "data" / ".pinterest_token.json"


def state_secret() -> str:
    return (
        _env("PINTEREST_STATE_SECRET")
        or _env("SECRET_KEY")
        or client_secret()
    )


def is_configured() -> bool:
    return bool(client_id() and client_secret() and redirect_uri())


def _basic_auth_header() -> str:
    raw = f"{client_id()}:{client_secret()}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _sign_state(ts: int, nonce: str) -> str:
    secret = state_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="Pinterest state secret is not configured")
    message = f"{ts}.{nonce}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_oauth_state() -> str:
    ts = int(time.time())
    nonce = secrets.token_urlsafe(18)
    return f"{ts}.{nonce}.{_sign_state(ts, nonce)}"


def validate_oauth_state(state: str) -> None:
    try:
        ts_raw, nonce, supplied = state.split(".", 2)
        ts = int(ts_raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc
    if abs(int(time.time()) - ts) > 20 * 60:
        raise HTTPException(status_code=400, detail="Expired OAuth state")
    expected = _sign_state(ts, nonce)
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=400, detail="Invalid OAuth state signature")


def oauth_authorize_url() -> str:
    if not is_configured():
        raise HTTPException(status_code=503, detail="Pinterest OAuth is not configured")
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": scopes(),
        "state": make_oauth_state(),
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def read_token() -> dict[str, Any] | None:
    path = token_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_token(data: dict[str, Any]) -> None:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    if payload.get("expires_in"):
        payload["expires_at"] = int(time.time()) + int(payload["expires_in"])
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


async def exchange_code(code: str) -> dict[str, Any]:
    if not is_configured():
        raise HTTPException(status_code=503, detail="Pinterest OAuth is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{api_base()}/oauth/token",
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
            },
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    token = resp.json()
    write_token(token)
    return token


async def refresh_token(token: dict[str, Any]) -> dict[str, Any]:
    refresh = token.get("refresh_token")
    if not refresh:
        raise HTTPException(status_code=401, detail="Pinterest refresh token is missing")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{api_base()}/oauth/token",
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "scope": scopes(),
            },
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    new_token = resp.json()
    # Keep refresh_token if Pinterest omits it on refresh.
    if not new_token.get("refresh_token") and refresh:
        new_token["refresh_token"] = refresh
    write_token(new_token)
    return new_token


async def access_token() -> str:
    token = read_token()
    if not token or not token.get("access_token"):
        raise HTTPException(status_code=401, detail="Pinterest is not connected — run OAuth")
    expires_at = int(token.get("expires_at") or 0)
    # Refresh one day before expiry when possible.
    if expires_at and expires_at - int(time.time()) < 24 * 60 * 60:
        token = await refresh_token(token)
    return str(token["access_token"])


async def api_request(method: str, path: str, **kwargs: Any) -> Any:
    token = await access_token()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.request(
            method,
            f"{api_base()}{path}",
            headers={"Authorization": f"Bearer {token}"},
            **kwargs,
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    if not resp.content:
        return {}
    return resp.json()


async def get_user_account() -> dict[str, Any]:
    return await api_request("GET", "/user_account")


async def list_boards(*, page_size: int = 100) -> dict[str, Any]:
    return await api_request("GET", "/boards", params={"page_size": page_size})


async def create_board(
    *,
    name: str,
    description: str = "",
    privacy: str = "PUBLIC",
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "privacy": privacy}
    if description:
        body["description"] = description
    return await api_request("POST", "/boards", json=body)


async def create_pin(
    *,
    board_id: str,
    title: str,
    description: str,
    link: str,
    image_url: str,
    alt_text: str = "",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "board_id": board_id,
        "title": title[:100],
        "description": description[:800],
        "link": link,
        "media_source": {
            "source_type": "image_url",
            "url": image_url,
        },
    }
    if alt_text:
        body["alt_text"] = alt_text[:500]
    return await api_request("POST", "/pins", json=body)


def product_pin_payload(detail: dict[str, Any]) -> dict[str, Any]:
    """Build pin fields from a product detail/public dict."""
    slug = (detail.get("slug") or "").strip()
    title = (detail.get("title") or "Reading accessory").strip()
    desc = (detail.get("description") or "").strip()
    if len(desc) > 440:
        desc = desc[:437].rstrip() + "..."
    price = detail.get("price_usd")
    price_bit = f" From ${float(price):.2f} USD." if price is not None else ""
    cta = " Shop at The Books Wanderer — literary boutique for readers."
    link = f"{public_base()}/products/{slug}?utm_source=pinterest&utm_medium=organic&utm_campaign=pin"
    img = (detail.get("image_url") or "").strip()
    if img.startswith("/"):
        img = public_base() + img
    return {
        "slug": slug,
        "title": title[:100],
        "description": f"{desc}{price_bit}{cta}".strip()[:800],
        "link": link,
        "image_url": img,
        "alt_text": title[:500],
    }
