#!/usr/bin/env python3
"""
Genera el video del anuncio a partir del catalogo real.

Estructura: portada de marca -> N productos con zoom lento, nombre y precio ->
cierre con la URL. Sale en 1080x1350 (4:5), que es el formato que Facebook
recomienda para el feed y el que mas pantalla ocupa en movil.

    python3 scripts/build_ad_video.py                 # los 6 por defecto
    python3 scripts/build_ad_video.py --slugs a,b,c   # elegir productos
    python3 scripts/build_ad_video.py --out /tmp/x.mp4

Requiere ffmpeg y las fuentes DejaVu (ambos en el VPS).

DOS TRAMPAS QUE YA COSTARON UNA VUELTA, no reintroducirlas:

1. zoompan expande CADA fotograma de entrada en `d` fotogramas de salida. Con
   `-loop 1 -t D` en la ENTRADA, D*fps fotogramas se convierten en (D*fps)^2 y
   un clip de 2,4 s acaba durando casi tres minutos. El recorte va en la
   SALIDA: entrada en bucle infinito y `-t D` despues del filtro.

2. ffmpeg se invoca con lista de argumentos, nunca via shell. Un precio como
   "$7.99" dentro de comillas dobles en bash se expande como el parametro
   posicional $7 y en el video aparece ".99".
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path

W, H, FPS = 1080, 1350, 30
DUR = 2.4
CREAM = "#F8F2E5"
CREAM_HEX = "0xF8F2E5"
GREEN = "0x1B3728"
GOLD = "0xA97C22"
GOLD_LIGHT = "0xE2C47C"

FONTS = Path("/usr/share/fonts/truetype/dejavu")
SERIF = FONTS / "DejaVuSerif.ttf"
SERIF_B = FONTS / "DejaVuSerif-Bold.ttf"
SANS_B = FONTS / "DejaVuSans-Bold.ttf"

POR_DEFECTO = [
    "hollow-kitten-bookmark",
    "paper-butterfly-bookmark-set",
    "wooden-finger-book-holder",
    "kindle-magnetic-sleeve",
    "stacked-books-table-lamp",
    "wooden-reading-tracker",
]

BASE = "https://thebookswanderer.com"


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def catalogo(slugs: list[str]) -> list[dict]:
    with urllib.request.urlopen(f"{BASE}/api/products?limit=60", timeout=30) as r:
        data = json.load(r)
    por_slug = {p["slug"]: p for p in data["products"]}
    salida = []
    for s in slugs:
        p = por_slug.get(s)
        if not p:
            print(f"  aviso: no existe el producto {s}, se omite")
            continue
        url = p["image_url"]
        if url.startswith("/"):
            url = BASE + url
        salida.append({"title": p["title"], "price": p["price_usd"], "url": url})
    return salida


def portada(dst: Path) -> None:
    vf = (
        f"drawtext=fontfile={SANS_B}:text='LITERARY BOUTIQUE':fontcolor={GOLD}:"
        f"fontsize=34:x=(w-tw)/2:y=440:alpha='min(1,(t-0.2)*2)',"
        f"drawtext=fontfile={SERIF_B}:text='The Books Wanderer':fontcolor={GREEN}:"
        f"fontsize=86:x=(w-tw)/2:y=520:alpha='min(1,(t-0.4)*2)',"
        f"drawbox=x=(iw-180)/2:y=680:w=180:h=4:color={GOLD}@0.9:t=fill,"
        f"drawtext=fontfile={SERIF}:text='For those who wander between pages':"
        f"fontcolor=0x2B5240:fontsize=40:x=(w-tw)/2:y=740:alpha='min(1,(t-0.8)*2)',"
        f"fade=t=out:st=2.2:d=0.4:c={CREAM_HEX}"
    )
    ff("-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d=2.6:r={FPS}",
       "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-r", str(FPS), str(dst))


def producto(img: Path, titulo: str, precio: float, dst: Path) -> None:
    t = titulo.replace(":", r"\:").replace("'", "")
    # El backslash escapa el $ para drawtext, no para el shell: aqui no hay shell.
    p = f"${precio:.2f}".replace("$", r"\$")
    n = int(DUR * FPS)
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"zoompan=z='min(zoom+0.0012,1.16)':d={n}:x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
        f"drawbox=x=0:y={H-300}:w={W}:h=300:color=black@0.45:t=fill,"
        f"drawtext=fontfile={SERIF_B}:text='{t}':fontcolor=white:fontsize=50:"
        f"x=(w-tw)/2:y={H-232},"
        f"drawtext=fontfile={SANS_B}:text='{p}':fontcolor={GOLD_LIGHT}:"
        f"fontsize=62:x=(w-tw)/2:y={H-152},"
        f"fade=t=in:st=0:d=0.3:c={CREAM_HEX},"
        f"fade=t=out:st={DUR-0.3:.2f}:d=0.3:c={CREAM_HEX}"
    )
    # -t va DESPUES del filtro: recorta la salida, no la entrada. Ver cabecera.
    ff("-loop", "1", "-i", str(img), "-vf", vf, "-t", str(DUR),
       "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
       "-r", str(FPS), str(dst))


def cierre(dst: Path) -> None:
    vf = (
        f"drawtext=fontfile={SERIF_B}:text='Small things':fontcolor={GREEN}:"
        f"fontsize=76:x=(w-tw)/2:y=520,"
        f"drawtext=fontfile={SERIF_B}:text='that make reading a ritual':"
        f"fontcolor={GREEN}:fontsize=56:x=(w-tw)/2:y=625,"
        f"drawbox=x=(iw-180)/2:y=730:w=180:h=4:color={GOLD}@0.9:t=fill,"
        f"drawtext=fontfile={SANS_B}:text='thebookswanderer.com':fontcolor={GOLD}:"
        f"fontsize=46:x=(w-tw)/2:y=790,"
        f"drawtext=fontfile={SERIF}:text='Shipping priced per destination':"
        f"fontcolor=0x5C6157:fontsize=32:x=(w-tw)/2:y=880,"
        f"fade=t=in:st=0:d=0.4:c={CREAM_HEX}"
    )
    ff("-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d=2.8:r={FPS}",
       "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-r", str(FPS), str(dst))


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera el video del anuncio.")
    ap.add_argument("--slugs", default=",".join(POR_DEFECTO))
    ap.add_argument("--out", default="/root/tbw-ad.mp4")
    args = ap.parse_args()

    productos = catalogo([s.strip() for s in args.slugs.split(",") if s.strip()])
    if not productos:
        raise SystemExit("Ningun producto valido.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clips = tmp / "clip"
        clips.mkdir()

        portada(clips / "00.mp4")
        for i, p in enumerate(productos, start=1):
            img = tmp / f"{i}.jpg"
            urllib.request.urlretrieve(p["url"], img)
            producto(img, p["title"], p["price"], clips / f"{i:02d}.mp4")
            print(f"  {i:02d} {p['title']:<34} ${p['price']:.2f}")
        cierre(clips / "99.mp4")

        lista = tmp / "list.txt"
        lista.write_text(
            "".join(f"file '{c}'\n" for c in sorted(clips.glob("*.mp4")))
        )
        ff("-f", "concat", "-safe", "0", "-i", str(lista),
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", "-r", str(FPS), args.out)

    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", args.out],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"\n{args.out} — {dur}s, {W}x{H}")


if __name__ == "__main__":
    main()
