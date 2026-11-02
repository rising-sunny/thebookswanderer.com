"""Owner-only product image management, using the existing administrator login."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from live import ADMIN_COOKIE, _admin_password, templates
from models import Product
from routers.collaborators import browser_admin
from services import product_media as media

router = APIRouter(include_in_schema=False)


def csrf_token(request: Request) -> str:
    value = "product-media:" + request.cookies.get(ADMIN_COOKIE, "")
    return hmac.new(_admin_password().encode(), value.encode(), hashlib.sha256).hexdigest()


def require_write(request: Request, csrf: str):
    if not browser_admin(request):
        raise HTTPException(401, "Administrator authentication required")
    if not hmac.compare_digest(csrf_token(request).encode(), csrf.encode()):
        raise HTTPException(403, "Invalid form token")


def render(request, db, product_id=0, error="", saved=False, status_code=200):
    products = db.query(Product).order_by(Product.id.desc()).all()
    product = db.get(Product, product_id) if product_id else None
    if product_id and not product:
        raise HTTPException(404, "Product not found")
    images = media.gallery(product) if product else []
    return templates.TemplateResponse(request, "admin_product_media.html", {
        "products": products, "product": product, "images": images,
        "csrf": csrf_token(request), "revision": media.revision(product) if product else "",
        "upload_prefix": media.PREFIX, "error": error, "saved": saved,
    }, status_code=status_code, headers={
        "Cache-Control": "no-store, private", "X-Robots-Tag": "noindex, nofollow",
        "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; img-src 'self' https:; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'self'",
    })


@router.get("/admin/product-media/", response_class=HTMLResponse)
def page(request: Request, product_id: int = 0, saved: bool = False, db: Session = Depends(get_db)):
    if not browser_admin(request):
        return RedirectResponse("/admin/live/login", status_code=303)
    return render(request, db, product_id, saved=saved)


@router.post("/admin/product-media/append", response_class=HTMLResponse)
async def append(request: Request, product_id: int = Form(...), revision: str = Form(...),
                 csrf: str = Form(""), origin: str = Form(...), disclosed: bool = Form(False),
                 files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    require_write(request, csrf)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    try:
        if len(files) > media.MAX_BATCH:
            raise media.MediaError("Añade como máximo tres imágenes cada vez.")
        data = [await f.read(media.MAX_BYTES + 1) for f in files]
        media.append(db, product, revision, data, origin=origin, disclosed=disclosed)
    except media.MediaError as exc:
        db.rollback()
        return render(request, db, product_id, error=str(exc), status_code=400)
    except OSError:
        db.rollback()
        return render(request, db, product_id, error="No se pudieron guardar las imágenes. Revisa el almacenamiento del VPS.", status_code=503)
    finally:
        for f in files:
            await f.close()
    return RedirectResponse(f"/admin/product-media/?product_id={product_id}&saved=1", status_code=303)


@router.post("/admin/product-media/remove", response_class=HTMLResponse)
def remove(request: Request, product_id: int = Form(...), revision: str = Form(...),
           csrf: str = Form(""), url: str = Form(...), db: Session = Depends(get_db)):
    require_write(request, csrf)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    try:
        media.remove(db, product, revision, url)
    except media.MediaError as exc:
        db.rollback()
        return render(request, db, product_id, error=str(exc), status_code=400)
    except OSError:
        db.rollback()
        return render(request, db, product_id, error="No se pudo guardar el respaldo. Revisa el almacenamiento del VPS.", status_code=503)
    return RedirectResponse(f"/admin/product-media/?product_id={product_id}&saved=1", status_code=303)
