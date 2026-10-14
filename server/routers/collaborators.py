"""Private collaborator inbox; shares the existing Live administrator login."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import os
import sqlite3
import time
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.routing import APIRoute

from live import ADMIN_COOKIE, ADMIN_MAX_AGE, _admin_password, _admin_user, _valid_cookie, templates
from services import collaborators_store as store
from services.collaborators import ResearchError, normalize_url


class PrivateRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        @wraps(original)
        async def handler(request):
            try:
                response = await original(request)
            except (OSError, sqlite3.Error):
                response = JSONResponse({"detail": "La bandeja no está disponible temporalmente. Revisa el almacenamiento privado del servidor."}, status_code=503)
            response.headers.update({
                "Cache-Control": "no-store, private", "X-Robots-Tag": "noindex, nofollow, nosnippet",
                "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            })
            return response
        return handler


router = APIRouter(route_class=PrivateRoute, include_in_schema=False)


def local_date(value):
    if not value:
        return "Todavía no revisada"
    return datetime.fromisoformat(value).astimezone(ZoneInfo("America/Santiago")).strftime("%d/%m/%Y %H:%M")


templates.env.filters["collaborator_date"] = local_date


def browser_admin(request: Request) -> bool:
    cookie = request.cookies.get(ADMIN_COOKIE, "")
    try:
        if not _admin_password() or not _valid_cookie(cookie):
            return False
        stamp, username, _ = cookie.split(".")
        age = time.time() - int(stamp)
        return 0 <= age <= ADMIN_MAX_AGE and hmac.compare_digest(username, _admin_user())
    except (ValueError, TypeError):
        return False


def api_admin(request: Request) -> bool:
    key = os.getenv("SECRET_KEY", "")
    supplied = request.headers.get("x-admin-key", "")
    return bool(key and supplied and hmac.compare_digest(key.encode(), supplied.encode()))


def require_read(request: Request):
    if not browser_admin(request) and not api_admin(request):
        raise HTTPException(401, "Administrator authentication required")


def csrf_token(request: Request) -> str:
    cookie = request.cookies.get(ADMIN_COOKIE, "")
    # HMAC binds the form to the authenticated, HttpOnly session. No secret key
    # is ever embedded in HTML or persisted in the browser's local storage.
    return hmac.new(_admin_password().encode(), ("collaborators:" + cookie).encode(), hashlib.sha256).hexdigest()


def require_write(request: Request, csrf: str):
    if api_admin(request):
        return
    if not browser_admin(request):
        raise HTTPException(401, "Administrator authentication required")
    if not hmac.compare_digest(csrf_token(request).encode(), csrf.encode()):
        raise HTTPException(403, "Invalid form token")


def filters(status: str, lang: str):
    if status and status not in store.STATUSES:
        raise HTTPException(400, "Invalid status")
    if lang and lang not in ("es", "en"):
        raise HTTPException(400, "Invalid language")


@router.get("/admin/collaborators", response_class=HTMLResponse)
def inbox(request: Request, status: str = "", lang: str = ""):
    if not browser_admin(request) and not api_admin(request):
        return RedirectResponse("/admin/live/login", status_code=303)
    filters(status, lang)
    data = store.snapshot(status, lang)
    return templates.TemplateResponse(request, "admin_collaborators.html", {
        "request": request, **data, "csrf": csrf_token(request),
        "selected_status": status, "selected_lang": lang,
        "labels": {"pending": "Pendiente", "approved": "Aprobado", "discarded": "Descartado", "contacted": "Contactado"},
    })


@router.get("/api/admin/collaborators")
def list_candidates(request: Request, status: str = "", lang: str = ""):
    require_read(request)
    filters(status, lang)
    return store.snapshot(status, lang)


def csv_cell(value) -> str:
    value = str(value or "")
    # Neutralize spreadsheet formulas, including whitespace-prefixed variants.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value


@router.get("/admin/collaborators/export.csv")
def export(request: Request, status: str = "approved", lang: str = ""):
    require_read(request)
    filters(status, lang)
    rows = store.snapshot(status, lang, limit=None)["candidates"]
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    fields = ("name", "email", "lang", "category", "reason", "source_url", "evidence", "purpose", "status", "notes", "found_at", "last_seen_at")
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_cell(row.get(field)) for field in fields])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="colaboradores.csv"'})


@router.post("/admin/collaborators/candidates/{candidate_id}")
def update_candidate(request: Request, candidate_id: int, status: str = Form(...), notes: str = Form("", max_length=2000), csrf: str = Form("")):
    require_write(request, csrf)
    filters(status, "")
    if not status:
        raise HTTPException(400, "Status required")
    with store.connect() as db:
        cursor = db.execute("UPDATE candidates SET status=?,notes=?,updated_at=? WHERE id=?", (status, notes, store.now(), candidate_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Candidate not found")
    return RedirectResponse("/admin/collaborators", status_code=303)


@router.post("/admin/collaborators/sources")
def add_source(request: Request, name: str = Form(..., min_length=1, max_length=150), url: str = Form(..., max_length=500), lang: str = Form(...), category: str = Form(..., min_length=1, max_length=100), reason: str = Form(..., min_length=1, max_length=500), csrf: str = Form("")):
    require_write(request, csrf)
    filters("", lang)
    if not lang:
        raise HTTPException(400, "Language required")
    if not all(value.strip() for value in (name, category, reason)):
        raise HTTPException(400, "Completa el nombre, el tipo y el motivo de afinidad.")
    try:
        url = normalize_url(url)
    except ResearchError as exc:
        raise HTTPException(400, str(exc)) from exc
    with store.connect() as db:
        if db.execute("SELECT count(*) FROM sources").fetchone()[0] >= 250:
            raise HTTPException(400, "Source limit reached")
        db.execute("INSERT OR IGNORE INTO sources(name,url,lang,category,reason) VALUES(?,?,?,?,?)", (name.strip(), url, lang, category.strip(), reason.strip()))
    return RedirectResponse("/admin/collaborators#fuentes", status_code=303)


@router.post("/admin/collaborators/sources/{source_id}")
def update_source(request: Request, source_id: int, active: int = Form(...), csrf: str = Form("")):
    require_write(request, csrf)
    if active not in (0, 1):
        raise HTTPException(400, "Invalid source state")
    with store.connect() as db:
        cursor = db.execute("UPDATE sources SET active=? WHERE id=?", (active, source_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Source not found")
    return RedirectResponse("/admin/collaborators#fuentes", status_code=303)
