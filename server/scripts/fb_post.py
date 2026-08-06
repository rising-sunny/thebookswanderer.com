#!/usr/bin/env python3
"""
Publica en la Página de Facebook de The Books Wanderer vía Graph API.

No existe MCP oficial para el feed orgánico de una Página (el de Meta Ads solo
gestiona campañas), así que esto es la vía directa.

Configurar en server/.env:
    FB_PAGE_ID=...
    FB_PAGE_TOKEN=...      # Page Access Token, long-lived,
                           # con pages_manage_posts + pages_read_engagement

Uso:
    # comprobar que el token sirve, sin publicar nada
    python fb_post.py whoami

    # texto
    python fb_post.py text "Mensaje" --link https://thebookswanderer.com

    # una foto (ruta local o URL) o varias -> carrusel
    python fb_post.py photo assets/logo.png --message "Texto"
    python fb_post.py photo a.jpg b.jpg c.jpg --message "Swipe →"

    # video
    python fb_post.py video demo.mp4 --message "Texto" --title "Titulo"

    # programar (10 min a 30 dias vista, hora local del servidor)
    python fb_post.py text "Hola" --schedule "2026-08-02 10:00"

    # ver que se enviaria sin llamar a Meta
    python fb_post.py text "Hola" --dry-run

El token nunca se imprime, ni siquiera en los errores.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 120  # los videos tardan


def _env_file() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> tuple[str, str]:
    if load_dotenv:
        load_dotenv(_env_file())
    page_id = (os.getenv("FB_PAGE_ID") or "").strip()
    token = (os.getenv("FB_PAGE_TOKEN") or "").strip()
    if not page_id or not token:
        sys.exit(
            "Faltan FB_PAGE_ID y/o FB_PAGE_TOKEN.\n"
            f"Anadelos a {_env_file()} y vuelve a intentarlo."
        )
    return page_id, token


def _scrub(text: str, token: str) -> str:
    """Que un token no acabe nunca en un log o en una consola."""
    return text.replace(token, "<TOKEN>") if token else text


def _token_info(token: str) -> dict:
    """Tipo, caducidad y permisos reales del token, segun Meta."""
    try:
        resp = httpx.get(
            f"{GRAPH}/debug_token",
            params={"input_token": token, "access_token": token},
            timeout=30,
        )
        if resp.status_code >= 400:
            return {}
        return resp.json().get("data", {})
    except Exception:  # noqa: BLE001
        return {}


def _resolve_page_token(page_id: str, token: str) -> str:
    """Devuelve un token capaz de publicar en la Pagina.

    El feed de una Pagina solo acepta un Page Access Token. Si en .env hay un
    token de usuario -- lo habitual, porque es lo que devuelve el Graph API
    Explorer -- se cambia aqui por el de la Pagina, que es exactamente lo que
    haria /me/accounts a mano. Asi el .env guarda un solo token y no hay que
    renovar dos.
    """
    info = _token_info(token)
    if (info.get("type") or "").upper() == "PAGE":
        return token

    resp = httpx.get(
        f"{GRAPH}/me/accounts",
        params={"access_token": token, "fields": "id,name,access_token"},
        timeout=30,
    )
    if resp.status_code >= 400:
        sys.exit(
            "El token es de usuario y no se pudo obtener el de la Pagina:\n"
            + _scrub(resp.text, token)[:500]
        )
    for page in resp.json().get("data", []):
        if str(page.get("id")) == str(page_id):
            return page.get("access_token") or token

    nombres = ", ".join(p.get("name", "?") for p in resp.json().get("data", [])) or "ninguna"
    sys.exit(
        f"El token no da acceso a la Pagina {page_id}.\n"
        f"Paginas visibles con este token: {nombres}"
    )


def _parse_schedule(value: str | None) -> int | None:
    """Meta exige entre 10 minutos y 30 dias vista."""
    if not value:
        return None
    try:
        when = datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        sys.exit('Formato de fecha invalido. Usa "AAAA-MM-DD HH:MM".')
    now = datetime.now()
    if when < now + timedelta(minutes=10):
        sys.exit("Meta exige programar con al menos 10 minutos de antelacion.")
    if when > now + timedelta(days=30):
        sys.exit("Meta no permite programar a mas de 30 dias.")
    return int(when.timestamp())


def _post(url: str, data: dict, token: str, files=None, dry_run=False) -> dict:
    shown = {k: v for k, v in data.items() if k != "access_token"}
    if dry_run:
        print(f"[dry-run] POST {url}")
        print(f"[dry-run] {json.dumps(shown, ensure_ascii=False, indent=2)}")
        if files:
            print(f"[dry-run] adjunto: {list(files)}")
        return {"dry_run": True}

    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(url, data=data, files=files)
    if resp.status_code >= 400:
        sys.exit(f"Meta rechazo la peticion ({resp.status_code}):\n"
                 f"{_scrub(resp.text, token)[:900]}")
    return resp.json()


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def cmd_whoami(args, page_id: str, token: str) -> None:
    """Verifica el token sin publicar nada."""
    info = _token_info(token)
    tipo = (info.get("type") or "?").upper()
    scopes = info.get("scopes", [])
    caduca = "nunca" if info.get("expires_at") == 0 else str(info.get("expires_at"))

    print(f"Token     : tipo {tipo}, caduca {caduca}, valido={info.get('is_valid')}")
    if tipo == "USER":
        print("            (de usuario: se derivara el de la Pagina al publicar)")

    page_token = _resolve_page_token(page_id, token)

    resp = httpx.get(
        f"{GRAPH}/{page_id}",
        params={"fields": "name,link,fan_count,category", "access_token": page_token},
        timeout=30,
    )
    if resp.status_code >= 400:
        sys.exit(f"El token no sirve para esta Pagina:\n{_scrub(resp.text, token)[:600]}")

    d = resp.json()
    print(f"Pagina    : {d.get('name')}")
    print(f"ID        : {page_id}")
    print(f"Categoria : {d.get('category', '(sin categoria)')}")
    print(f"Seguidores: {d.get('fan_count', 0)}")
    print(f"URL       : {d.get('link', '')}")

    faltan = [p for p in ("pages_manage_posts", "pages_read_engagement")
              if scopes and p not in scopes]
    if faltan:
        print(f"\nAVISO: faltan permisos: {', '.join(faltan)}. No podra publicar.")
    else:
        print("\nPermisos de publicacion presentes. Listo para publicar.")


def cmd_text(args, page_id: str, token: str) -> None:
    data = {"message": args.message, "access_token": token}
    if args.link:
        data["link"] = args.link
    when = _parse_schedule(args.schedule)
    if when:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(when)
    out = _post(f"{GRAPH}/{page_id}/feed", data, token, dry_run=args.dry_run)
    _report(out, page_id, args)


def cmd_photo(args, page_id: str, token: str) -> None:
    when = _parse_schedule(args.schedule)

    # Una sola foto: se publica directamente con su texto.
    if len(args.images) == 1:
        data = {"access_token": token, "message": args.message or ""}
        files = None
        src = args.images[0]
        if _is_url(src):
            data["url"] = src
        else:
            path = Path(src)
            if not path.exists():
                sys.exit(f"No existe el archivo: {src}")
            files = {"source": (path.name, path.read_bytes())}
        if when:
            data["published"] = "false"
            data["scheduled_publish_time"] = str(when)
        out = _post(f"{GRAPH}/{page_id}/photos", data, token, files=files,
                    dry_run=args.dry_run)
        _report(out, page_id, args)
        return

    # Varias fotos: subir cada una sin publicar y adjuntarlas a un post del feed.
    media_ids = []
    for src in args.images:
        data = {"access_token": token, "published": "false"}
        files = None
        if _is_url(src):
            data["url"] = src
        else:
            path = Path(src)
            if not path.exists():
                sys.exit(f"No existe el archivo: {src}")
            files = {"source": (path.name, path.read_bytes())}
        up = _post(f"{GRAPH}/{page_id}/photos", data, token, files=files,
                   dry_run=args.dry_run)
        media_ids.append(up.get("id", "<dry-run>"))
        print(f"  subida: {src} -> {media_ids[-1]}")

    data = {"access_token": token, "message": args.message or ""}
    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    if when:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(when)
    out = _post(f"{GRAPH}/{page_id}/feed", data, token, dry_run=args.dry_run)
    _report(out, page_id, args)


def cmd_video(args, page_id: str, token: str) -> None:
    path = Path(args.file)
    if not path.exists():
        sys.exit(f"No existe el archivo: {args.file}")
    data = {"access_token": token, "description": args.message or ""}
    if args.title:
        data["title"] = args.title
    when = _parse_schedule(args.schedule)
    if when:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(when)
    files = {"source": (path.name, path.read_bytes())}
    print(f"Subiendo {path.name} ({path.stat().st_size // 1024} KB)...")
    out = _post(f"{GRAPH}/{page_id}/videos", data, token, files=files,
                dry_run=args.dry_run)
    _report(out, page_id, args)


def _report(out: dict, page_id: str, args) -> None:
    if out.get("dry_run"):
        print("\n[dry-run] Nada se publico.")
        return
    post_id = out.get("post_id") or out.get("id", "")
    print("\nPublicado." if not args.schedule else "\nProgramado.")
    print(f"ID: {post_id}")
    if post_id:
        print(f"Ver: https://www.facebook.com/{post_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Publica en la Pagina de Facebook.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Muestra lo que se enviaria sin llamar a Meta.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("whoami", help="Comprueba el token, no publica.")
    p.set_defaults(func=cmd_whoami, schedule=None)

    p = sub.add_parser("text", help="Publicacion de solo texto.")
    p.add_argument("message")
    p.add_argument("--link")
    p.add_argument("--schedule")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("photo", help="Una foto, o varias como carrusel.")
    p.add_argument("images", nargs="+", help="Rutas locales o URLs.")
    p.add_argument("--message")
    p.add_argument("--schedule")
    p.set_defaults(func=cmd_photo)

    p = sub.add_parser("video", help="Sube un video.")
    p.add_argument("file")
    p.add_argument("--message")
    p.add_argument("--title")
    p.add_argument("--schedule")
    p.set_defaults(func=cmd_video)

    args = ap.parse_args()
    page_id, token = _load_env()

    # whoami hace su propia resolucion; en dry-run no se toca la red.
    if args.func is not cmd_whoami and not args.dry_run:
        token = _resolve_page_token(page_id, token)

    args.func(args, page_id, token)


if __name__ == "__main__":
    main()
