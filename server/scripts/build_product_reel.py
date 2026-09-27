#!/usr/bin/env python3
"""
Reel vertical de UN producto: 1080x1920, las fotos del catalogo, precio final
y la URL de la ficha.

    python3 scripts/build_product_reel.py modern-bookends-pair --out /root/reel.mp4

Distinto de build_ad_video.py, que recorre varios productos del catalogo. Aqui
manda un solo producto y el cierre lleva el precio y el enlace, que es lo que
un reel de producto necesita para convertir.

Trampas heredadas de build_ad_video.py, no reintroducirlas:
  1. zoompan expande CADA fotograma de entrada en `d` de salida: el recorte
     (-t) va en la SALIDA, con la entrada en bucle infinito.
  2. ffmpeg se invoca con lista de argumentos, nunca por shell: "$39.99" entre
     comillas dobles en bash se expande como el parametro posicional $3.
  3. Las fotos verticales muy alargadas del proveedor (790x1870) son
     infografias, no producto: se descartan por proporcion.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path

W, H, FPS = 1080, 1920, 30
DUR = 2.6
CREAM, CREAM_HEX = "#F8F2E5", "0xF8F2E5"
GREEN, GOLD, GOLD_LIGHT = "0x1B3728", "0xA97C22", "0xE2C47C"
F = Path("/usr/share/fonts/truetype/dejavu")
SERIF, SERIF_B, SANS_B = F / "DejaVuSerif.ttf", F / "DejaVuSerif-Bold.ttf", F / "DejaVuSans-Bold.ttf"
BASE = "https://thebookswanderer.com"


def ff(*a: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


def dims(p: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(p)],
        capture_output=True, text=True,
    ).stdout.strip()
    w, h = out.split("x")[:2]
    return int(w), int(h)


def producto(slug: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/api/products/by-slug/{slug}", timeout=30) as r:
        return json.load(r)


def portada(dst: Path, titulo: str) -> None:
    c = H // 2
    vf = (
        f"drawtext=fontfile={SANS_B}:text='THE BOOKS WANDERER':fontcolor={GOLD}:"
        f"fontsize=32:x=(w-tw)/2:y={c-210}:alpha='min(1,(t-0.2)*2)',"
        f"drawtext=fontfile={SERIF_B}:text='{titulo}':fontcolor={GREEN}:"
        f"fontsize=76:x=(w-tw)/2:y={c-130}:alpha='min(1,(t-0.4)*2)',"
        f"drawbox=x=(iw-180)/2:y={c+10}:w=180:h=4:color={GOLD}@0.9:t=fill,"
        f"fade=t=out:st={DUR-0.4:.2f}:d=0.4:c={CREAM_HEX}"
    )
    ff("-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d={DUR}:r={FPS}",
       "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-r", str(FPS), str(dst))


def foto(img: Path, dst: Path, rotulo: str = "") -> None:
    n = int(DUR * FPS)
    # Encajada entera sobre crema: recortar a 9:16 partiria el producto.
    encaje = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={CREAM},")
    banda = ""
    if rotulo:
        t = rotulo.replace(":", r"\:").replace("'", "")
        banda = (f"drawbox=x=0:y={H-210}:w={W}:h=210:color=black@0.45:t=fill,"
                 f"drawtext=fontfile={SERIF_B}:text='{t}':fontcolor=white:"
                 f"fontsize=54:x=(w-tw)/2:y={H-140},")
    vf = (f"{encaje}"
          f"zoompan=z='min(zoom+0.0011,1.14)':d={n}:x='iw/2-(iw/zoom/2)':"
          f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
          f"{banda}"
          f"fade=t=in:st=0:d=0.3:c={CREAM_HEX},"
          f"fade=t=out:st={DUR-0.3:.2f}:d=0.3:c={CREAM_HEX}")
    ff("-loop", "1", "-i", str(img), "-vf", vf, "-t", str(DUR),
       "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
       "-r", str(FPS), str(dst))


def cierre(dst: Path, titulo: str, precio: float, url: str) -> None:
    c = H // 2
    # El backslash escapa el $ para drawtext; aqui no hay shell que lo expanda.
    p = f"${precio:.2f}".replace("$", r"\$")
    vf = (
        f"drawtext=fontfile={SERIF_B}:text='{titulo}':fontcolor={GREEN}:"
        f"fontsize=68:x=(w-tw)/2:y={c-220},"
        f"drawtext=fontfile={SANS_B}:text='{p}':fontcolor={GOLD}:"
        f"fontsize=120:x=(w-tw)/2:y={c-110},"
        f"drawbox=x=(iw-180)/2:y={c+60}:w=180:h=4:color={GOLD}@0.9:t=fill,"
        f"drawtext=fontfile={SERIF}:text='Free worldwide shipping':"
        f"fontcolor=0x2B5240:fontsize=42:x=(w-tw)/2:y={c+110},"
        f"drawtext=fontfile={SANS_B}:text='{url}':fontcolor=0x5C6157:"
        f"fontsize=30:x=(w-tw)/2:y={c+200},"
        f"fade=t=in:st=0:d=0.4:c={CREAM_HEX}"
    )
    ff("-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d=3.4:r={FPS}",
       "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-r", str(FPS), str(dst))


def main() -> None:
    ap = argparse.ArgumentParser(description="Reel vertical de un producto.")
    ap.add_argument("slug")
    ap.add_argument("--out", default="/root/reel.mp4")
    ap.add_argument("--max-fotos", type=int, default=5)
    args = ap.parse_args()

    p = producto(args.slug)
    titulo, precio = p["title"], float(p["price_usd"])
    url = f"thebookswanderer.com/products/{args.slug}"

    # Variantes primero (muestran las opciones), luego lifestyle.
    urls, vistos = [], set()
    for v in p.get("variants") or []:
        u = (v.get("image_url") or "").strip()
        if u and u not in vistos:
            vistos.add(u); urls.append((u, v.get("name") or ""))
    for u in p.get("lifestyle_images") or []:
        if u and u not in vistos:
            vistos.add(u); urls.append((u, ""))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clips = tmp / "c"; clips.mkdir()
        portada(clips / "00.mp4", titulo)

        n = 0
        for u, rotulo in urls:
            if n >= args.max_fotos:
                break
            img = tmp / f"i{n}.jpg"
            try:
                urllib.request.urlretrieve(u, img)
                w, h = dims(img)
            except Exception as e:  # noqa: BLE001
                print(f"  omitida ({e}): {u[:60]}"); continue
            if min(w, h) < 500:
                print(f"  omitida (demasiado pequena {w}x{h}): {u[:60]}"); continue
            if h / w > 1.9:  # infografia larga del proveedor, no producto
                print(f"  omitida (infografia {w}x{h}): {u[:60]}"); continue
            n += 1
            foto(img, clips / f"{n:02d}.mp4", rotulo)
            print(f"  {n:02d} {w}x{h} {rotulo or '(lifestyle)'}")

        if not n:
            raise SystemExit("ninguna imagen utilizable")
        cierre(clips / "99.mp4", titulo, precio, url)

        lista = tmp / "l.txt"
        lista.write_text("".join(f"file '{c}'\n" for c in sorted(clips.glob("*.mp4"))))
        ff("-f", "concat", "-safe", "0", "-i", str(lista),
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", "-r", str(FPS), args.out)

    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", args.out], capture_output=True, text=True).stdout.strip()
    print(f"\n{args.out} — {float(dur):.1f}s, {W}x{H}, {n} fotos")


if __name__ == "__main__":
    main()
