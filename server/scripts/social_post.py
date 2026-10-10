#!/usr/bin/env python3
"""
Publica lo mismo en la Pagina de Facebook y en Instagram con un solo comando.

Es una capa fina sobre fb_post.py e ig_post.py: no repite su logica, solo
adapta el texto a cada red y publica en las dos.

    # reel / video
    python social_post.py reel demo.mp4 --caption-file texto.txt \\
        --link https://thebookswanderer.com/products/modern-bookends-pair

    # una foto o carrusel (URLs publicas, que es lo que Instagram acepta)
    python social_post.py photo https://.../a.jpg https://.../b.jpg --caption "Texto"

    # ver que se enviaria a cada red sin publicar
    python social_post.py --dry-run reel demo.mp4 --caption "Hola" --link https://...

El enlace (--link) va al final del texto: en Facebook como URL, en Instagram
como "Link in bio", porque alli los enlaces del texto no son clicables. No
pongas la URL dentro del propio texto.

Si una red falla, la otra se publica igual y al final se dice cual fallo, para
reintentar solo esa con fb_post.py o ig_post.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fb_post
import ig_post


def _caption(args) -> str:
    if args.caption_file:
        return Path(args.caption_file).read_text(encoding="utf-8").strip()
    return (args.caption or "").strip()


def _con_enlace(texto: str, enlace: str) -> str:
    """Inserta el enlace antes del bloque final de hashtags, si lo hay."""
    if not enlace:
        return texto
    partes = texto.rsplit("\n\n", 1)
    if len(partes) == 2 and partes[1].lstrip().startswith("#"):
        return f"{partes[0]}\n{enlace}\n\n{partes[1]}"
    return f"{texto}\n\n{enlace}"


def _facebook(args, texto: str) -> None:
    page_id, token = fb_post._load_env()
    if not args.dry_run:
        token = fb_post._resolve_page_token(page_id, token)
    if args.cmd == "reel":
        ns = argparse.Namespace(file=args.file, message=texto, title=args.title,
                                schedule=None, dry_run=args.dry_run)
        fb_post.cmd_video(ns, page_id, token)
    else:
        ns = argparse.Namespace(images=args.images, message=texto,
                                schedule=None, dry_run=args.dry_run)
        fb_post.cmd_photo(ns, page_id, token)


def _instagram(args, texto: str) -> None:
    page_id, token = fb_post._load_env()
    token = fb_post._resolve_page_token(page_id, token)
    ig_id, username = ig_post._ig_account(page_id, token)
    ns = argparse.Namespace(caption=texto, caption_file=None, dry_run=args.dry_run)
    if args.cmd == "reel":
        ns.file, ns.thumb_offset, ns.no_feed = args.file, args.thumb_offset, False
        ig_post.cmd_reel(ns, ig_id, username, token)
    else:
        ns.images = args.images
        ig_post.cmd_photo(ns, ig_id, username, token)


def main() -> None:
    ap = argparse.ArgumentParser(description="Publica en Facebook e Instagram.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Muestra lo que se enviaria a cada red sin publicar.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def comunes(p):
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--caption")
        g.add_argument("--caption-file", help="Texto desde un archivo (multilinea).")
        p.add_argument("--link", help="URL: tal cual en Facebook, 'Link in bio' en Instagram.")

    p = sub.add_parser("reel", help="Video: reel en Instagram, video en Facebook.")
    p.add_argument("file")
    comunes(p)
    p.add_argument("--title", help="Titulo del video en Facebook.")
    p.add_argument("--thumb-offset", type=int, help="Milisegundo de portada en Instagram.")

    p = sub.add_parser("photo", help="Una foto, o varias como carrusel.")
    p.add_argument("images", nargs="+", help="URLs publicas.")
    comunes(p)

    args = ap.parse_args()
    if args.cmd == "reel" and not Path(args.file).exists():
        sys.exit(f"No existe el archivo: {args.file}")
    if args.cmd == "photo":
        for src in args.images:
            if not fb_post._is_url(src):
                sys.exit(f"Usa URLs publicas (Instagram no acepta archivos): {src}")

    texto = _caption(args)
    texto_fb = _con_enlace(texto, args.link or "")
    texto_ig = _con_enlace(texto, "Link in bio 📚" if args.link else "")
    # Validar el texto de Instagram antes de publicar nada: es la red mas
    # estricta, y fallar a medias deja una red publicada y la otra no.
    ig_post._caption(argparse.Namespace(caption=texto_ig, caption_file=None))

    fallos = []
    for nombre, publicar, txt in (("Facebook", _facebook, texto_fb),
                                  ("Instagram", _instagram, texto_ig)):
        print(f"\n=== {nombre} ===")
        try:
            publicar(args, txt)
        except SystemExit as exc:  # fb_post/ig_post salen con sys.exit
            print(exc.code if isinstance(exc.code, str) else f"Fallo ({exc.code})")
            fallos.append(nombre)
        except Exception as exc:  # noqa: BLE001  timeouts de red, sobre todo
            print(f"Fallo: {type(exc).__name__}")
            fallos.append(nombre)

    if fallos:
        sys.exit(f"\nNo se publico en: {', '.join(fallos)}. "
                 "Reintenta solo esa red con fb_post.py o ig_post.py.")
    print("\nListo en Facebook e Instagram." if not args.dry_run
          else "\n[dry-run] Nada se publico en ninguna red.")


if __name__ == "__main__":
    main()
