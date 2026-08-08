"""Pinterest OAuth + admin helpers for The Books Wanderer."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Product
from services import pinterest as pin

router = APIRouter(tags=["pinterest"])


def _admin_ok(key: str | None) -> bool:
    secret = (os.getenv("SECRET_KEY") or "").strip()
    return bool(secret and key and key == secret)


def _require_admin(admin_key: str = Query(..., description="SECRET_KEY")) -> None:
    if not _admin_ok(admin_key):
        raise HTTPException(403, "Invalid admin key")


class PinProductIn(BaseModel):
    admin_key: str
    board_id: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)


class BoardCreateIn(BaseModel):
    admin_key: str
    name: str = Field(..., min_length=1, max_length=180)
    description: str = Field("", max_length=500)
    privacy: str = Field("PUBLIC", pattern="^(PUBLIC|PROTECTED|SECRET)$")


@router.get("/api/pinterest/oauth/start")
async def oauth_start(admin_key: str = Query(...)):
    """Begin OAuth — open this while logged into the TBW Pinterest account."""
    _require_admin(admin_key)
    return RedirectResponse(pin.oauth_authorize_url(), status_code=302)


@router.get("/api/pinterest/oauth/callback")
async def oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
):
    if error:
        detail = error_description or error
        raise HTTPException(status_code=400, detail=detail)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth code or state")
    pin.validate_oauth_state(state)
    await pin.exchange_code(code)
    account: dict[str, Any] | None = None
    try:
        account = await pin.get_user_account()
    except HTTPException:
        account = None
    username = (account or {}).get("username") or (account or {}).get("business_name") or "connected"
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><title>Pinterest connected</title>
<meta name="robots" content="noindex">
<style>
body{{font-family:system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1rem;line-height:1.5}}
code{{background:#f4f0e6;padding:.1rem .35rem;border-radius:4px}}
</style>
</head><body>
<h1>Pinterest connected</h1>
<p>Token saved for <strong>{username}</strong>.</p>
<p>Next: <code>python scripts/pinterest_cli.py whoami</code>
or <code>python scripts/pinterest_cli.py boards</code></p>
<p><a href="/">Back to shop</a></p>
</body></html>"""
    return HTMLResponse(html)


@router.get("/api/pinterest/status")
async def status(_: None = Depends(_require_admin)):
    token = pin.read_token()
    connected = bool(token and token.get("access_token"))
    account = None
    if connected:
        try:
            account = await pin.get_user_account()
        except HTTPException as exc:
            account = {"error": str(exc.detail)}
    return {
        "configured": pin.is_configured(),
        "connected": connected,
        "redirect_uri": pin.redirect_uri(),
        "api_base": pin.api_base(),
        "scopes": pin.scope_list(),
        "token_file": str(pin.token_path()),
        "expires_at": token.get("expires_at") if token else None,
        "account": account,
    }


@router.get("/api/pinterest/boards")
async def boards(_: None = Depends(_require_admin)):
    return await pin.list_boards()


@router.post("/api/pinterest/boards")
async def boards_create(body: BoardCreateIn):
    if not _admin_ok(body.admin_key):
        raise HTTPException(403, "Invalid admin key")
    return await pin.create_board(
        name=body.name,
        description=body.description,
        privacy=body.privacy,
    )


@router.post("/api/pinterest/pins/product")
async def pin_product(body: PinProductIn, db: Session = Depends(get_db)):
    if not _admin_ok(body.admin_key):
        raise HTTPException(403, "Invalid admin key")
    p = (
        db.query(Product)
        .filter(Product.slug == body.slug.strip(), Product.active.is_(True))
        .first()
    )
    if not p:
        raise HTTPException(404, "Product not found")
    detail = p.to_detail()
    payload = pin.product_pin_payload(detail)
    if not payload.get("image_url"):
        raise HTTPException(400, "Product has no image_url")
    created = await pin.create_pin(
        board_id=body.board_id,
        title=payload["title"],
        description=payload["description"],
        link=payload["link"],
        image_url=payload["image_url"],
        alt_text=payload["alt_text"],
    )
    return {"ok": True, "product": payload["slug"], "pin": created}
