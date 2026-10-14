"""Signed opt-out for invitations. GET confirms; POST applies the opt-out."""
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from services import outreach

router = APIRouter(include_in_schema=False)


def page(title: str, body: str, lang: str) -> HTMLResponse:
    return HTMLResponse(f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{title} · The Books Wanderer</title></head><body style="margin:0;padding:40px 20px;background:#f8f2e5;color:#1b3728;font:16px/1.6 system-ui,sans-serif"><main style="max-width:560px;margin:auto;background:#fffdf8;padding:30px;border:1px solid #e0d4b8;border-radius:12px"><p>The Books Wanderer</p><h1 style="font-family:Georgia,serif">{title}</h1>{body}</main></body></html>''', headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex,nofollow", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})


def validate(email: str, token: str, lang: str) -> str:
    if lang not in ("es", "en") or len(email) > 254 or len(token) != 32 or not outreach.valid_unsubscribe(email, token):
        raise HTTPException(400, "Invalid unsubscribe link")
    return outreach.normalized_email(email)


@router.get("/api/outreach/unsubscribe", response_class=HTMLResponse)
def confirm(email: str, t: str, lang: str = "es"):
    email = validate(email, t, lang)
    url = "/api/outreach/unsubscribe?" + urlencode({"email": email, "t": t, "lang": lang})
    title = "Dejar de recibir invitaciones" if lang == "es" else "Stop receiving invitations"
    label = "Confirmar baja" if lang == "es" else "Confirm unsubscribe"
    text = "Confirma si no deseas recibir más mensajes promocionales en" if lang == "es" else "Confirm that you no longer want promotional emails at"
    body = f'<p>{text} <strong>{escape(email)}</strong>.</p><form method="post" action="{escape(url, quote=True)}"><button type="submit" style="padding:12px 20px;background:#2b5240;color:white;border:0;border-radius:8px;font:inherit">{label}</button></form>'
    return page(title, body, lang)


@router.post("/api/outreach/unsubscribe", response_class=HTMLResponse)
def unsubscribe(email: str, t: str, lang: str = "es"):
    email = validate(email, t, lang)
    outreach.suppress(email)
    title = "Baja confirmada" if lang == "es" else "You're unsubscribed"
    text = "No te enviaremos más invitaciones ni mensajes promocionales. Los correos relacionados con tus compras no cambian." if lang == "es" else "We won't send more invitations or promotional emails. Emails about your purchases are unaffected."
    return page(title, f'<p>{text}</p><a href="/">The Books Wanderer</a>', lang)
