#!/usr/bin/env python3
"""
Publica en el Instagram de The Books Wanderer (@thebooks.wanderer) via Graph API.

Usa el mismo token que fb_post.py: la cuenta de Instagram es la vinculada a la
Pagina, asi que no hay nada nuevo que configurar en server/.env.

Uso:
    # comprobar cuenta y cupo de publicaciones, sin publicar nada
    python ig_post.py whoami

    # reel (archivo local; se sube directamente a Meta)
    python ig_post.py reel demo.mp4 --caption "Texto"
    python ig_post.py reel demo.mp4 --caption-file caption.txt --thumb-offset 3000

    # una foto o varias -> carrusel (URLs publicas: Instagram no acepta
    # imagenes subidas, las descarga el mismo)
    python ig_post.py photo https://.../a.jpg --caption "Texto"
    python ig_post.py photo https://.../a.jpg https://.../b.jpg --caption "Swipe"

    # ver que se enviaria sin llamar a Meta
    python ig_post.py --dry-run reel demo.mp4 --caption "Hola"

Publicar en Instagram son varios pasos: crear el contenedor, subir el video,
esperar a que Meta lo procese y publicarlo. El ultimo paso a veces se corta por
timeout aunque la publicacion si sale; por eso, ante un fallo, se mira el
estado del contenedor antes de reintentar. Reintentar a ciegas duplica el post.

Los enlaces en el texto de Instagram no son clicables: usa "Link in bio".
El token nunca se imprime, ni siquiera en los errores.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from fb_post import GRAPH, _is_url, _load_env, _resolve_page_token, _scrub

TIMEOUT = 120
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
POLL_EVERY, POLL_MAX = 6, 100  # hasta 10 minutos procesando


def _get(path: str, params: dict, token: str) -> dict:
    resp = httpx.get(f"{GRAPH}/{path}", params={**params, "access_token": token},
                     timeout=60)
    if resp.status_code >= 400:
        sys.exit(f"Meta rechazo la peticion ({resp.status_code}):\n"
                 f"{_scrub(resp.text, token)[:900]}")
    return resp.json()


def _post(path: str, data: dict, token: str, dry_run=False) -> dict:
    if dry_run:
        print(f"[dry-run] POST {GRAPH}/{path}")
        print(f"[dry-run] {json.dumps(data, ensure_ascii=False, indent=2)}")
        return {"id": "<dry-run>"}
    resp = httpx.post(f"{GRAPH}/{path}", data={**data, "access_token": token},
                      timeout=TIMEOUT)
    if resp.status_code >= 400:
        sys.exit(f"Meta rechazo la peticion ({resp.status_code}):\n"
                 f"{_scrub(resp.text, token)[:900]}")
    return resp.json()


def _ig_account(page_id: str, token: str) -> tuple[str, str]:
    d = _get(page_id, {"fields": "instagram_business_account{id,username}"}, token)
    ig = d.get("instagram_business_account")
    if not ig:
        sys.exit("La Pagina no tiene una cuenta de Instagram profesional vinculada.")
    return ig["id"], ig.get("username", "?")


def _caption(args) -> str:
    text = args.caption or ""
    if args.caption_file:
        text = Path(args.caption_file).read_text(encoding="utf-8").strip()
    if len(text) > MAX_CAPTION:
        sys.exit(f"El texto tiene {len(text)} caracteres; Instagram admite {MAX_CAPTION}.")
    tags = sum(1 for w in text.split() if w.startswith("#"))
    if tags > MAX_HASHTAGS:
        sys.exit(f"{tags} hashtags; Instagram admite {MAX_HASHTAGS} y rechaza el post.")
    if "http://" in text or "https://" in text:
        print("AVISO: los enlaces en el texto de Instagram no son clicables.")
    return text


def _wait_ready(cid: str, token: str) -> None:
    """Meta procesa el video aparte; publicar antes de FINISHED falla."""
    for _ in range(POLL_MAX):
        st = _get(cid, {"fields": "status_code,status"}, token)
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            sys.exit(f"Meta no pudo procesar el contenedor: {st.get('status')}")
        time.sleep(POLL_EVERY)
    sys.exit(f"El contenedor {cid} sigue procesandose; reintenta mas tarde.")


def _publish(ig_id: str, cid: str, token: str, dry_run: bool) -> None:
    """Publica el contenedor sin riesgo de duplicar si la llamada se corta."""
    if dry_run:
        _post(f"{ig_id}/media_publish", {"creation_id": cid}, token, dry_run=True)
        print("\n[dry-run] Nada se publico.")
        return

    media_id = None
    for intento in range(3):
        try:
            resp = httpx.post(f"{GRAPH}/{ig_id}/media_publish",
                              data={"creation_id": cid, "access_token": token},
                              timeout=TIMEOUT)
            if resp.status_code < 400:
                media_id = resp.json().get("id")
                break
            error = _scrub(resp.text, token)[:900]
        except httpx.HTTPError as exc:
            error = type(exc).__name__
        # Antes de reintentar: puede que si haya salido.
        time.sleep(5)
        if _get(cid, {"fields": "status_code"}, token).get("status_code") == "PUBLISHED":
            break
        print(f"  publicar fallo ({error[:120]}), reintento {intento + 1}...")
    else:
        sys.exit(f"No se pudo publicar el contenedor {cid}:\n{error}")

    if not media_id:  # salio, pero no sabemos su id: es el mas reciente
        data = _get(f"{ig_id}/media", {"fields": "id", "limit": 1}, token).get("data", [])
        media_id = data[0]["id"] if data else ""
    link = _get(media_id, {"fields": "permalink"}, token).get("permalink", "") if media_id else ""
    print("\nPublicado.")
    print(f"ID: {media_id}")
    if link:
        print(f"Ver: {link}")


def cmd_whoami(args, ig_id: str, username: str, token: str) -> None:
    d = _get(ig_id, {"fields": "username,name,followers_count,media_count"}, token)
    print(f"Cuenta    : @{d.get('username')} ({d.get('name', '')})")
    print(f"ID        : {ig_id}")
    print(f"Seguidores: {d.get('followers_count', 0)}")
    print(f"Posts     : {d.get('media_count', 0)}")
    lim = _get(f"{ig_id}/content_publishing_limit",
               {"fields": "quota_usage,config"}, token).get("data", [{}])[0]
    total = (lim.get("config") or {}).get("quota_total", "?")
    print(f"Cupo 24h  : {lim.get('quota_usage', '?')} de {total} publicaciones usadas")


def cmd_reel(args, ig_id: str, username: str, token: str) -> None:
    path = Path(args.file)
    if not path.exists():
        sys.exit(f"No existe el archivo: {args.file}")
    data = {"media_type": "REELS", "upload_type": "resumable",
            "caption": _caption(args),
            "share_to_feed": "false" if args.no_feed else "true"}
    if args.thumb_offset is not None:
        data["thumb_offset"] = str(args.thumb_offset)
    out = _post(f"{ig_id}/media", data, token, dry_run=args.dry_run)
    cid = out["id"]

    size = path.stat().st_size
    print(f"Subiendo {path.name} ({size // 1024} KB) a @{username}...")
    if not args.dry_run:
        uri = out.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{cid}"
        resp = httpx.post(uri, content=path.read_bytes(), timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
        if resp.status_code >= 400:
            sys.exit(f"Fallo la subida ({resp.status_code}):\n{_scrub(resp.text, token)[:600]}")
        print("Procesando en Meta...")
        _wait_ready(cid, token)
    _publish(ig_id, cid, token, args.dry_run)


def cmd_photo(args, ig_id: str, username: str, token: str) -> None:
    for src in args.images:
        if not _is_url(src):
            sys.exit(f"Instagram solo acepta imagenes por URL publica: {src}")
    if len(args.images) > 10:
        sys.exit("Un carrusel admite como maximo 10 imagenes.")
    caption = _caption(args)

    if len(args.images) == 1:
        out = _post(f"{ig_id}/media", {"image_url": args.images[0], "caption": caption},
                    token, dry_run=args.dry_run)
    else:
        hijos = []
        for src in args.images:
            h = _post(f"{ig_id}/media", {"image_url": src, "is_carousel_item": "true"},
                      token, dry_run=args.dry_run)
            hijos.append(h["id"])
            print(f"  subida: {src} -> {h['id']}")
        out = _post(f"{ig_id}/media", {"media_type": "CAROUSEL", "caption": caption,
                                       "children": ",".join(hijos)},
                    token, dry_run=args.dry_run)
    if not args.dry_run:
        _wait_ready(out["id"], token)
    _publish(ig_id, out["id"], token, args.dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(description="Publica en el Instagram de la marca.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Muestra lo que se enviaria sin publicar.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("whoami", help="Comprueba cuenta y cupo, no publica.")
    p.set_defaults(func=cmd_whoami)

    def caption_args(p):
        g = p.add_mutually_exclusive_group()
        g.add_argument("--caption")
        g.add_argument("--caption-file", help="Texto desde un archivo (multilinea).")

    p = sub.add_parser("reel", help="Sube un video como reel.")
    p.add_argument("file")
    caption_args(p)
    p.add_argument("--thumb-offset", type=int, help="Milisegundo usado de portada.")
    p.add_argument("--no-feed", action="store_true",
                   help="Solo en la pestana de reels, no en el feed.")
    p.set_defaults(func=cmd_reel)

    p = sub.add_parser("photo", help="Una foto, o varias como carrusel.")
    p.add_argument("images", nargs="+", help="URLs publicas.")
    caption_args(p)
    p.set_defaults(func=cmd_photo)

    args = ap.parse_args()
    page_id, token = _load_env()
    # La cuenta vinculada se consulta incluso en dry-run: es solo lectura.
    token = _resolve_page_token(page_id, token)
    ig_id, username = _ig_account(page_id, token)
    args.func(args, ig_id, username, token)


if __name__ == "__main__":
    main()
