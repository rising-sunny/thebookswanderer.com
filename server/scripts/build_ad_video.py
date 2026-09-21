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

# 4:5 para el feed de Facebook, 9:16 para TikTok / Reels / Stories.
FORMATOS = {"feed": (1080, 1350), "vertical": (1080, 1920)}

# Solo se traducen la portada y el cierre. Los nombres de producto y los precios
# se quedan como estan porque es lo que el comprador va a encontrar en la web,
# que esta en ingles: traducirlos aqui crearia un desajuste al aterrizar.
TEXTOS = {
    "en": {
        "eyebrow": "LITERARY BOUTIQUE",
        "tagline": "For those who wander between pages",
        "cierre1": "Small things",
        "cierre2": "that make reading a ritual",
        "cierre3": "Free worldwide shipping",
    },
    # Con acentos: drawtext + DejaVu los renderiza sin problema, comprobado.
    # Escribirlos sin tilde para "evitar riesgos" delata el texto como generado
    # y arruina justo la ventaja de anunciarse en el idioma del mercado.
    "es": {
        "eyebrow": "BOUTIQUE LITERARIA",
        "tagline": "Para quienes vagan entre páginas",
        "cierre1": "Objetos pequeños",
        "cierre2": "que hacen del leer un ritual",
        "cierre3": "Envío gratis a todo el mundo",
    },
}
T = TEXTOS["en"]
W, H, FPS = 1080, 1350, 30
DUR = 2.4
CREAM = "#F8F2E5"
CREAM_HEX = "0xF8F2E5"
GREEN = "0x1B3728"
GOLD = "0xA97C22"
GOLD_LIGHT = "0xE2C47C"
GREEN_BG = "#1B3728"

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


def variantes(slug: str) -> tuple[list[dict], str]:
    """One product's designs as separate clips.

    A single-product ad has nothing to cut between, so the colourways carry
    the montage: the label under each frame is the design, not the price,
    which appears once at the end instead of on every frame.
    """
    with urllib.request.urlopen(f"{BASE}/api/products/by-slug/{slug}", timeout=30) as r:
        p = json.load(r)
    salida, vistas = [], set()
    for v in p.get("variants") or []:
        url = (v.get("image_url") or "").strip()
        if not url:
            continue
        if url.startswith("/"):
            url = BASE + url
        # Una misma foto sirve a varias variantes cuando el catalogo cruza
        # acabado con talla (el atril son 3 fotos repartidas en 9 variantes).
        # Sin esto el montaje repite el mismo plano seis veces.
        if url in vistas:
            continue
        vistas.add(url)
        salida.append({"title": v.get("name") or "", "price": None, "url": url})
    if not salida:
        raise SystemExit(f"{slug} has no variant images")
    return salida, p.get("title") or slug


def portada(dst: Path) -> None:
    # Anclado al centro del alto para que sirva en 4:5 y en 9:16.
    c = H // 2
    vf = (
        f"drawtext=fontfile={SANS_B}:text='{T['eyebrow']}':fontcolor={GOLD}:"
        f"fontsize=34:x=(w-tw)/2:y={c-235}:alpha='min(1,(t-0.2)*2)',"
        f"drawtext=fontfile={SERIF_B}:text='The Books Wanderer':fontcolor={GREEN}:"
        f"fontsize=86:x=(w-tw)/2:y={c-155}:alpha='min(1,(t-0.4)*2)',"
        f"drawbox=x=(iw-180)/2:y={c+5}:w=180:h=4:color={GOLD}@0.9:t=fill,"
        f"drawtext=fontfile={SERIF}:text='{T['tagline']}':"
        f"fontcolor=0x2B5240:fontsize=40:x=(w-tw)/2:y={c+65}:alpha='min(1,(t-0.8)*2)',"
        f"fade=t=out:st=2.2:d=0.4:c={CREAM_HEX}"
    )
    ff("-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d=2.6:r={FPS}",
       "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-r", str(FPS), str(dst))


def bandas(iw: int, ih: int, titulo: str | None,
           medio=None) -> tuple[str, int | None]:
    """Encaje en bandas verdes con el rotulo arriba. Devuelve (filtro, pie).

    `pie` es la Y donde acaba la imagen: ahi se apoya la franja de envio.
    Es None cuando la imagen llena el cuadro y no hay banda.

    `medio` recibe el alto del encaje y devuelve filtros a insertar ANTES
    del relleno. El zoom va ahi: aplicado despues, ampliaria tambien las
    bandas y se comeria el rotulo.
    """
    alto = 2 * round(W * ih / iw / 2)
    if alto >= H:
        partes = [f"scale={W}:{H}:force_original_aspect_ratio=increase:"
                  f"flags=lanczos", f"crop={W}:{H}"]
        if medio:
            partes.append(medio(H))
        return ",".join(partes), None

    # La banda de abajo es la mayor: ahi se apilan los controles de Reels y
    # TikTok. Verde de marca y no crema: el crema alrededor de una foto de
    # fondo oscuro la enmarca como una caja de television vieja.
    arriba = 2 * round((H - alto) * 0.42 / 2)
    partes = [f"scale={W}:{alto}:flags=lanczos"]
    if medio:
        partes.append(medio(alto))
    partes.append(f"pad={W}:{H}:0:{arriba}:color={GREEN_BG}")
    if titulo and arriba >= 150:
        t = titulo.replace(":", r"\:").replace("'", "")
        # Se apoya en el pie de la banda y encoge hasta librar la chapa del
        # precio: su diagonal baja hacia la derecha, asi que cuanto mas
        # abajo va el rotulo, mas sitio le queda.
        lado = lado_chapa()
        for fs in range(52, 29, -2):
            y = arriba - fs - 26
            limite = W if y >= lado else W - lado + y - 12
            # 0.62 em es el avance medio de DejaVu Serif Bold; estimar basta,
            # el margen de 12 px absorbe el error.
            if W / 2 + 0.62 * fs * len(t) / 2 <= limite:
                break
        partes.append(f"drawtext=fontfile={SERIF_B}:text='{t}':"
                      f"fontcolor={CREAM_HEX}:fontsize={fs}:x=(w-tw)/2:y={y}")
    return ",".join(partes), arriba + alto


def producto(img: Path, titulo: str, precio: float | None, dst: Path,
             con_bandas: bool = False) -> int | None:
    t = titulo.replace(":", r"\:").replace("'", "")
    # El backslash escapa el $ para drawtext, no para el shell: aqui no hay shell.
    p = f"${precio:.2f}".replace("$", r"\$") if precio is not None else ""
    n = int(DUR * FPS)
    if con_bandas:
        # El montaje de disenos comparte marco con los anuncios de metraje:
        # el nombre del diseno va en la banda de arriba y la de abajo queda
        # libre para la franja de envio, que si no se solapa con el rotulo.
        iw, ih, _ = sonda(img)
        zoom = (lambda a: f"zoompan=z='min(zoom+0.0012,1.16)':d={n}:"
                          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                          f"s={W}x{a}:fps={FPS}")
        encaje, pie = bandas(iw, ih, titulo, medio=zoom)
        vf = (f"{encaje},fade=t=in:st=0:d=0.3:c={CREAM_HEX},"
              f"fade=t=out:st={DUR-0.3:.2f}:d=0.3:c={CREAM_HEX}")
        ff("-loop", "1", "-i", str(img), "-vf", vf, "-t", str(DUR),
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-r", str(FPS), str(dst))
        return pie
    # En 9:16 las fotos de catalogo (casi cuadradas) perderian medio producto al
    # recortarlas, asi que se encajan enteras sobre fondo crema. En 4:5 el
    # recorte apenas quita nada y llena mejor el marco.
    if H / W > 1.5:
        encaje = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={CREAM},"
        )
    else:
        encaje = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
    # Sin precio la banda es mas baja y el nombre va centrado en ella: una caja
    # de 300 px con una sola linea deja un hueco negro evidente.
    if p:
        banda = (
            f"drawbox=x=0:y={H-300}:w={W}:h=300:color=black@0.45:t=fill,"
            f"drawtext=fontfile={SERIF_B}:text='{t}':fontcolor=white:fontsize=50:"
            f"x=(w-tw)/2:y={H-232},"
            f"drawtext=fontfile={SANS_B}:text='{p}':fontcolor={GOLD_LIGHT}:"
            f"fontsize=62:x=(w-tw)/2:y={H-152},"
        )
    else:
        banda = (
            f"drawbox=x=0:y={H-190}:w={W}:h=190:color=black@0.45:t=fill,"
            f"drawtext=fontfile={SERIF_B}:text='{t}':fontcolor=white:fontsize=52:"
            f"x=(w-tw)/2:y={H-128},"
        )
    vf = (
        f"{encaje}"
        f"zoompan=z='min(zoom+0.0012,1.16)':d={n}:x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
        f"{banda}"
        f"fade=t=in:st=0:d=0.3:c={CREAM_HEX},"
        f"fade=t=out:st={DUR-0.3:.2f}:d=0.3:c={CREAM_HEX}"
    )
    # -t va DESPUES del filtro: recorta la salida, no la entrada. Ver cabecera.
    ff("-loop", "1", "-i", str(img), "-vf", vf, "-t", str(DUR),
       "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
       "-r", str(FPS), str(dst))


def sonda(src: Path) -> tuple[int, int, float]:
    """Ancho, alto y duracion del metraje. Los tres hacen falta antes de filtrar."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    w, h = (int(x) for x in out[0].split(",")[:2])
    return w, h, float(out[1])


def metraje(src: Path, dst: Path, *, start: float, dur: float,
            titulo: str | None = None, entra: bool = True,
            sale: bool = True) -> tuple[float, int | None]:
    """Real product footage, normalised to the output frame.

    Audio is dropped rather than reconciled: the brand cards are silent, the
    concat demuxer needs identical streams, and Meta autoplays muted anyway.
    """
    iw, ih, total = sonda(src)
    # Pedir mas metraje del que hay deja el fade de salida sin disparar y el
    # clip termina de golpe contra la tarjeta de cierre.
    dur = min(dur, max(0.5, total - start))
    encaje, pie = bandas(iw, ih, titulo)

    # Encadenando varios tramos, solo el primero entra desde crema y solo el
    # ultimo sale hacia el: fundir en cada corte mete destellos de crema en
    # mitad del cuerpo del anuncio.
    filtros = [encaje]
    if entra:
        filtros.append(f"fade=t=in:st=0:d=0.4:c={CREAM_HEX}")
    if sale:
        filtros.append(f"fade=t=out:st={dur - 0.5:.2f}:d=0.5:c={CREAM_HEX}")
    vf = ",".join(filtros)
    ff("-ss", str(start), "-i", str(src), "-t", str(dur), "-an", "-vf", vf,
       "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
       "-r", str(FPS), str(dst))
    return dur, pie


def cierre_producto(dst: Path, titulo: str, precio: float) -> None:
    """Closing card for a single-product ad: name, price, free shipping, URL."""
    c = H // 2
    t = titulo.replace(":", r"\:").replace("'", "")
    p = f"${precio:.2f}".replace("$", r"\$")
    vf = (
        f"drawtext=fontfile={SERIF_B}:text='{t}':fontcolor={GREEN}:"
        f"fontsize=64:x=(w-tw)/2:y={c-175},"
        f"drawtext=fontfile={SANS_B}:text='{p}':fontcolor={GOLD}:"
        f"fontsize=92:x=(w-tw)/2:y={c-75},"
        f"drawbox=x=(iw-180)/2:y={c+50}:w=180:h=4:color={GOLD}@0.9:t=fill,"
        f"drawtext=fontfile={SERIF}:text='{T['cierre3']}':fontcolor=0x2B5240:"
        f"fontsize=42:x=(w-tw)/2:y={c+100},"
        f"drawtext=fontfile={SANS_B}:text='thebookswanderer.com':fontcolor={GOLD}:"
        f"fontsize=46:x=(w-tw)/2:y={c+185},"
        f"fade=t=in:st=0:d=0.4:c={CREAM_HEX}"
    )
    ff("-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d=3.0:r={FPS}",
       "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-r", str(FPS), str(dst))


def cierre(dst: Path) -> None:
    c = H // 2
    vf = (
        f"drawtext=fontfile={SERIF_B}:text='{T['cierre1']}':fontcolor={GREEN}:"
        f"fontsize=76:x=(w-tw)/2:y={c-155},"
        f"drawtext=fontfile={SERIF_B}:text='{T['cierre2']}':"
        f"fontcolor={GREEN}:fontsize=56:x=(w-tw)/2:y={c-50},"
        f"drawbox=x=(iw-180)/2:y={c+55}:w=180:h=4:color={GOLD}@0.9:t=fill,"
        f"drawtext=fontfile={SANS_B}:text='thebookswanderer.com':fontcolor={GOLD}:"
        f"fontsize=46:x=(w-tw)/2:y={c+115},"
        f"drawtext=fontfile={SERIF}:text='{T['cierre3']}':"
        f"fontcolor=0x5C6157:fontsize=32:x=(w-tw)/2:y={c+205},"
        f"fade=t=in:st=0:d=0.4:c={CREAM_HEX}"
    )
    ff("-f", "lavfi", "-i", f"color=c={CREAM}:s={W}x{H}:d=2.8:r={FPS}",
       "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-r", str(FPS), str(dst))


def franja_envio(pie: int | None) -> str:
    """Franja de envio gratis, fija durante todo el anuncio.

    Se apoya en el borde inferior del metraje, no en el del cuadro: pegada
    abajo del todo caeria bajo los controles de Reels y TikTok, que ocupan
    los ultimos ~400 px. Sin bandas (formato feed) va sobre el metraje, a un
    margen del borde.
    """
    alto = 2 * round(H * 0.048 / 2)
    fuente = round(alto * 0.44)
    y = pie if pie is not None else H - alto - 48
    # drawtext no sabe espaciar letras y se separan a mano: apretada la franja
    # parece un boton, espaciada parece un sello.
    texto = "F R E E   S H I P P I N G"
    return (f"drawbox=x=0:y={y}:w={W}:h={alto}:color={GOLD}@1:t=fill,"
            f"drawtext=fontfile={SANS_B}:text='{texto}':fontcolor={CREAM_HEX}:"
            f"fontsize={fuente}:x=(w-tw)/2:y={y}+({alto}-th)/2")


def tramos(spec: str) -> list[tuple[float, float]]:
    """'inicio:duracion,inicio:duracion' -> [(2.75, 4.75), (10.35, 2.25)].

    El metraje del proveedor casi nunca se puede usar entero: trae rotulos,
    marcas de agua o, como en el tracker, un grabado personalizado que la
    tienda no vende. Recortar a mano cada trozo y concatenarlo aparte es la
    alternativa, y se pierde a la primera revision del anuncio.
    """
    salida = []
    for trozo in spec.split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        try:
            ini, dur = (float(x) for x in trozo.split(":"))
        except ValueError:
            raise SystemExit(f"tramo invalido: {trozo!r} (formato inicio:duracion)")
        salida.append((ini, dur))
    if not salida:
        raise SystemExit("--segments no define ningun tramo")
    return salida


def lado_chapa() -> int:
    """Lado de la chapa del precio. Lo consultan quien la dibuja y el rotulo
    del nombre, que tiene que apartarse de ella."""
    return 2 * round(W / 2.7 / 2)


def esquina_precio(precio: float, dst: Path) -> int:
    """Chapa triangular con el precio, pegada a la esquina superior derecha.

    Se genera una vez como PNG y luego se superpone: hacerla con filtros vivos
    obliga a geq a evaluar la expresion en cada fotograma del anuncio entero.

    Sin PIL, que no esta en el VPS: el triangulo es un cuadrado de color al que
    geq le recorta la mitad por la diagonal, y el precio va en un lienzo
    transparente aparte porque drawtext no sabe girar y hay que pasarlo por
    `rotate`.

    El texto se centra en el BARICENTRO del triangulo, (2L/3, L/3), no en el
    centro del cuadrado: centrado en el cuadrado la mitad se saldria por la
    hipotenusa y quedaria flotando fuera de la chapa.
    """
    lado = lado_chapa()
    fuente = round(lado * 0.15)
    p = f"${precio:.2f}".replace("$", r"\$")
    desplazo = lado // 6
    fc = (
        # a = distancia a la diagonal, saturada: da un borde con antialias en
        # vez del escalon que dejaria un if(gte(X,Y),255,0).
        f"[0:v]format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
        f"a='clip((X-Y)*255,0,255)'[tri];"
        # color= no propaga su alfa al convertir a rgba: el lienzo sale negro
        # opaco y la chapa acaba con un rectangulo detras del precio. El alfa
        # se pone despues, y rotate rellena con `none` para no reponerlo.
        f"[1:v]format=rgba,colorchannelmixer=aa=0,"
        f"drawtext=fontfile={SANS_B}:text='{p}':"
        f"fontcolor={CREAM_HEX}:fontsize={fuente}:x=(w-tw)/2:y=(h-th)/2,"
        f"rotate=PI/4:c=none:ow=rotw(PI/4):oh=roth(PI/4)[txt];"
        f"[tri][txt]overlay=x=(W-w)/2+{desplazo}:y=(H-h)/2-{desplazo}"
    )
    ff("-f", "lavfi", "-i", f"color=c={GOLD}:s={lado}x{lado}",
       "-f", "lavfi", "-i", f"color=c=black@0:s={lado}x{round(lado * 0.28)}",
       "-filter_complex", fc, "-frames:v", "1", str(dst))
    return lado


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera el video del anuncio.")
    ap.add_argument("--slugs", default=",".join(POR_DEFECTO))
    ap.add_argument("--out", default="/root/tbw-ad.mp4")
    ap.add_argument("--format", choices=sorted(FORMATOS), default="feed",
                    help="feed = 1080x1350 (Facebook), vertical = 1080x1920 "
                         "(TikTok, Reels, Stories).")
    ap.add_argument("--lang", choices=sorted(TEXTOS), default="en",
                    help="Idioma de la portada y el cierre. Los nombres de "
                         "producto no se traducen: la web esta en ingles.")
    ap.add_argument("--video", help="Metraje real. Sustituye a los clips de "
                                    "catalogo: portada + video + cierre.")
    ap.add_argument("--variantes", action="store_true",
                    help="Un solo producto contado por sus disenos, sin "
                         "metraje. Necesita --slug.")
    ap.add_argument("--slug", help="Producto del cierre cuando se usa --video.")
    ap.add_argument("--segments", help="Tramos del metraje, "
                                    "'inicio:duracion' separados por comas. "
                                    "Para saltarse lo que no se puede enseñar. "
                                    "Por defecto, --clip-start/--clip-dur.")
    ap.add_argument("--clip-start", type=float, default=0.0)
    ap.add_argument("--clip-dur", type=float, default=16.0)
    args = ap.parse_args()

    global W, H, T
    W, H = FORMATOS[args.format]
    T = TEXTOS[args.lang]

    productos: list[dict] = []
    remate = None
    pie = None
    if args.video or args.variantes:
        if not args.slug:
            raise SystemExit("--video y --variantes necesitan --slug")
        with urllib.request.urlopen(
            f"{BASE}/api/products/by-slug/{args.slug}", timeout=30
        ) as r:
            info = json.load(r)
        remate = (info.get("title") or args.slug, float(info.get("price_usd") or 0))
        if args.variantes:
            productos, _ = variantes(args.slug)
    else:
        productos = catalogo([s.strip() for s in args.slugs.split(",") if s.strip()])
        if not productos:
            raise SystemExit("Ningun producto valido.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clips = tmp / "clip"
        clips.mkdir()

        portada(clips / "00.mp4")
        if args.video:
            cortes = (tramos(args.segments) if args.segments
                      else [(args.clip_start, args.clip_dur)])
            for n, (ini, largo) in enumerate(cortes, start=1):
                usado, pie = metraje(
                    Path(args.video), clips / f"{n:02d}.mp4",
                    start=ini, dur=largo, titulo=remate[0],
                    entra=(n == 1), sale=(n == len(cortes)))
                print(f"  metraje {args.video} [{ini}s +{usado:.1f}s]")
            cierre_producto(clips / "99.mp4", remate[0], remate[1])
            print(f"  cierre  {remate[0]} ${remate[1]:.2f}")
        else:
            for i, p in enumerate(productos, start=1):
                img = tmp / f"{i}.jpg"
                urllib.request.urlretrieve(p["url"], img)
                pie = producto(img, p["title"], p["price"],
                               clips / f"{i:02d}.mp4", con_bandas=args.variantes)
                precio = f"${p['price']:.2f}" if p["price"] is not None else "—"
                print(f"  {i:02d} {p['title']:<34} {precio}")
            if remate:
                cierre_producto(clips / "99.mp4", remate[0], remate[1])
                print(f"  cierre  {remate[0]} ${remate[1]:.2f}")
            else:
                cierre(clips / "99.mp4")

        lista = tmp / "list.txt"
        lista.write_text(
            "".join(f"file '{c}'\n" for c in sorted(clips.glob("*.mp4")))
        )
        salida = ["-c:v", "libx264", "-preset", "veryfast",
                  "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                  "-r", str(FPS), args.out]
        if remate:
            chapa = tmp / "chapa.png"
            lado = esquina_precio(remate[1], chapa)
            ff("-f", "concat", "-safe", "0", "-i", str(lista), "-i", str(chapa),
               "-filter_complex",
               f"[0:v][1:v]overlay=x=main_w-{lado}:y=0,{franja_envio(pie)}",
               *salida)
        else:
            # En modo catalogo cada producto lleva su precio en su rotulo; una
            # sola cifra fija en la esquina mentiria sobre cinco de los seis.
            # La franja se va con ella: el cierre ya promete el envio gratis.
            ff("-f", "concat", "-safe", "0", "-i", str(lista), *salida)

    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", args.out],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"\n{args.out} — {dur}s, {W}x{H}")


if __name__ == "__main__":
    main()
