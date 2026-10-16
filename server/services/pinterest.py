"""Pinterest API v5 client for The Books Wanderer (own app + OAuth token)."""
from __future__ import annotations

import base64
import hmac
import json
import logging
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

logger = logging.getLogger("pinterest")

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


def free_shipping() -> bool:
    """Mirrors main.FREE_SHIPPING; read from env so this stays import-free."""
    return (os.getenv("FREE_SHIPPING", "1") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def reauth_warn_days() -> int:
    """Days before the refresh token dies that we start warning."""
    try:
        return max(1, int(os.getenv("PINTEREST_REAUTH_WARN_DAYS", "14")))
    except ValueError:
        return 14


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


def _file_owner(path: Path) -> tuple[int, int] | None:
    """(uid, gid) of an existing file, or None. No-op on Windows."""
    if not hasattr(os, "chown"):
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_uid, st.st_gid)


def _restore_owner(target: Path, owner: tuple[int, int] | None) -> None:
    """Keep the token file owned by whoever owned it before.

    The web app runs as www-data and the cron as root. Without this, a
    root-driven refresh replaces the file with a root:root 0600 one and the
    app silently loses access to its own token (read_token swallows the
    PermissionError and every call then looks like "not connected").
    Only root can hand a file to another user, so this is a no-op otherwise.
    """
    if not owner or not hasattr(os, "chown") or not hasattr(os, "geteuid"):
        return
    if os.geteuid() != 0:
        return
    try:
        os.chown(target, owner[0], owner[1])
    except OSError:
        logger.warning("could not restore token ownership to uid=%s gid=%s", *owner)


def write_token(data: dict[str, Any]) -> None:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    now = int(time.time())
    if payload.get("expires_in"):
        payload["expires_at"] = now + int(payload["expires_in"])
    # Pinterest sends this only on the initial grant; keep it absolute so the
    # hard re-OAuth deadline stays visible to monitoring.
    if payload.get("refresh_token_expires_in"):
        payload["refresh_token_expires_at"] = now + int(
            payload["refresh_token_expires_in"]
        )

    owner = _file_owner(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    _restore_owner(tmp, owner)
    os.replace(tmp, path)


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
    # Pinterest does not re-issue the refresh token on every refresh. Carry the
    # original deadline over, otherwise it vanishes after the first refresh and
    # we lose all warning before re-OAuth becomes mandatory.
    if not new_token.get("refresh_token_expires_in") and not new_token.get(
        "refresh_token_expires_at"
    ):
        previous = token.get("refresh_token_expires_at")
        if previous:
            new_token["refresh_token_expires_at"] = previous
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


def token_health() -> dict[str, Any]:
    """Expiry snapshot for monitoring. Never returns secrets.

    Two clocks matter: the access token (auto-refreshed) and the refresh
    token (hard deadline — only a manual OAuth round trip resets it).
    """
    token = read_token()
    if not token or not token.get("access_token"):
        return {
            "connected": False,
            "reauth_required": True,
            "reason": "no_token",
        }

    now = int(time.time())
    access_at = int(token.get("expires_at") or 0)
    refresh_at = int(token.get("refresh_token_expires_at") or 0)

    def days_left(ts: int) -> float | None:
        return round((ts - now) / 86400, 1) if ts else None

    refresh_days = days_left(refresh_at)
    return {
        "connected": True,
        "has_refresh_token": bool(token.get("refresh_token")),
        "access_expires_at": access_at or None,
        "access_expires_in_days": days_left(access_at),
        # No expires_at means write_token never saw expires_in: the access
        # token would never auto-refresh and dies silently.
        "access_autorefresh": bool(access_at),
        "refresh_expires_at": refresh_at or None,
        "refresh_expires_in_days": refresh_days,
        "refresh_expiry_known": bool(refresh_at),
        "reauth_required": bool(refresh_at and refresh_at <= now),
        "reauth_warning": bool(
            refresh_days is not None and 0 < refresh_days <= reauth_warn_days()
        ),
        "warn_days": reauth_warn_days(),
    }


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


async def create_video_pin(
    *,
    board_id: str,
    title: str,
    description: str,
    link: str,
    video_path: Path,
    cover_image_url: str,
    alt_text: str = "",
    timeout_s: int = 300,
) -> dict[str, Any]:
    """Register a video upload, send the file to Pinterest's upload URL,
    wait for processing, then create the pin."""
    import asyncio

    reg = await api_request("POST", "/media", json={"media_type": "video"})
    async with httpx.AsyncClient(timeout=300) as client:
        with open(video_path, "rb") as fh:
            up = await client.post(
                reg["upload_url"],
                data=reg.get("upload_parameters") or {},
                files={"file": (video_path.name, fh, "video/mp4")},
            )
    if up.status_code >= 300:
        raise HTTPException(status_code=up.status_code, detail=f"video upload failed: {up.text[:300]}")
    media_id = reg["media_id"]
    waited = 0
    while True:
        st = await api_request("GET", f"/media/{media_id}")
        status = (st.get("status") or "").lower()
        if status == "succeeded":
            break
        if status == "failed" or waited >= timeout_s:
            raise HTTPException(status_code=502, detail=f"video processing {status or 'timeout'}")
        await asyncio.sleep(5)
        waited += 5
    body: dict[str, Any] = {
        "board_id": board_id,
        "title": title[:100],
        "description": description[:800],
        "link": link,
        "media_source": {
            "source_type": "video_id",
            "media_id": media_id,
            "cover_image_url": cover_image_url,
        },
    }
    if alt_text:
        body["alt_text"] = alt_text[:500]
    return await api_request("POST", "/pins", json=body)


def shipping_copy(detail: dict[str, Any]) -> str:
    """Describe supported destinations without promising worldwide delivery."""
    supplier = detail.get("supplier") or "cj"
    if supplier == "digital":
        return "Instant PDF download; no physical shipping."
    if supplier == "printify":
        return "Printed to order. US delivery only." + (" Standard US shipping included." if free_shipping() else "")
    if supplier == "lulu":
        from services import lulu
        countries = ", ".join(sorted(lulu.ship_countries()))
        return f"Printed to order. Shipping included to: {countries}."
    return ("Standard US shipping included. " if free_shipping() else "") + "Check the product page for delivery availability."


def product_pin_payload(detail: dict[str, Any]) -> dict[str, Any]:
    """Build pin fields from a product detail/public dict."""
    slug = (detail.get("slug") or "").strip()
    title = (detail.get("title") or "Reading accessory").strip()
    desc = (detail.get("description") or "").strip()
    if len(desc) > 440:
        desc = desc[:437].rstrip() + "..."
    price = detail.get("price_usd")
    if price is None:
        price_bit = ""
    else:
        price_bit = f" From ${float(price):.2f} USD."
    price_bit += " " + shipping_copy(detail)
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
