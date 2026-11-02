"""Owner-only approval of Bonanza orders before the suppliers charge (services/bonanza_orders.py)."""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from live import ADMIN_COOKIE, _admin_password, templates
from models import BonanzaOrder
from routers.collaborators import browser_admin
from services import bonanza_orders as flow

router = APIRouter(include_in_schema=False)
HEADERS = {
    "Cache-Control": "no-store, private", "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
}


def csrf_token(request: Request) -> str:
    value = "bonanza-orders:" + request.cookies.get(ADMIN_COOKIE, "")
    return hmac.new(_admin_password().encode(), value.encode(), hashlib.sha256).hexdigest()


def require_write(request: Request, csrf: str):
    if not browser_admin(request):
        raise HTTPException(401, "Administrator authentication required")
    if not hmac.compare_digest(csrf_token(request).encode(), csrf.encode()):
        raise HTTPException(403, "Invalid form token")


def render(request, db, message="", error="", status_code=200):
    rows = db.query(BonanzaOrder).order_by(BonanzaOrder.created_at.desc()).limit(60).all()
    orders = [{"row": r, "summary": json.loads(r.summary_json or "{}")} for r in rows]
    return templates.TemplateResponse(request, "admin_bonanza_orders.html", {
        "orders": orders, "csrf": csrf_token(request), "message": message, "error": error,
    }, status_code=status_code, headers=HEADERS)


@router.get("/admin/bonanza/", response_class=HTMLResponse)
def page(request: Request, db: Session = Depends(get_db)):
    if not browser_admin(request):
        return RedirectResponse("/admin/live/login", status_code=303)
    return render(request, db)


@router.post("/admin/bonanza/{action}", response_class=HTMLResponse)
async def act(request: Request, action: str, ref: str = Form(...), csrf: str = Form(""), db: Session = Depends(get_db)):
    require_write(request, csrf)
    row = db.get(BonanzaOrder, ref)
    if not row or action not in {"approve", "dismiss"}:
        raise HTTPException(404, "Not found")
    try:
        if action == "approve":
            await flow.approve(db, row)
            return render(request, db, message=f"{ref}: sent to production. It will be marked shipped on Bonanza when the supplier ships.")
        await flow.dismiss(db, row)
        return render(request, db, message=f"{ref}: left for you to handle; the on-hold Printify order was cancelled.")
    except ValueError as exc:
        db.rollback()
        return render(request, db, error=str(exc), status_code=409)
