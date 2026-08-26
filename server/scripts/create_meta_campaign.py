#!/usr/bin/env python3
"""
Crea una campaña de Meta Ads completa (campaña + ad set + creatividad + anuncio)
en estado PAUSED, con un vídeo local como creatividad.

Existe porque el MCP oficial de Meta Ads necesita OAuth interactivo en el
navegador, y porque el vídeo suele vivir en la máquina del dueño, no en el
servidor. Esto se ejecuta donde está el vídeo.

Nada queda activo. Los cuatro objetos se crean en PAUSED y activarlos es una
decisión manual en Ads Manager.

Configurar en server/.env (o exportar en el entorno):
    META_ADS_TOKEN=...     # token de usuario con ads_management
    FB_PAGE_ID=...         # Página que firma el anuncio

Uso:
    # ver qué se enviaría, sin tocar Meta (no sube el vídeo)
    python scripts/create_meta_campaign.py \
        --account 1696378237957660 \
        --link https://thebookswanderer.com/products/butterfly-metal-bookmark \
        --video "C:/Users/sunse/Downloads/WASK-AI-CREATIVE-4310.mp4" \
        --daily-budget 5 \
        --dry-run

    # crear de verdad (todo en PAUSED)
    python scripts/create_meta_campaign.py \
        --account 1696378237957660 \
        --link https://thebookswanderer.com/products/butterfly-metal-bookmark \
        --video "C:/Users/sunse/Downloads/WASK-AI-CREATIVE-4310.mp4" \
        --daily-budget 5

--daily-budget se expresa SIEMPRE en unidades enteras de la moneda de la
cuenta (5 = 5 USD, o 5 CLP si la cuenta fuese en pesos). El script consulta la
moneda real antes de convertir a unidades menores, porque ese es el error que
vacía un presupuesto: en CLP no hay decimales y `5000` son 5.000 pesos, pero en
USD `5000` serían 50 dólares — diez veces lo previsto.

El token no se imprime nunca, ni siquiera dentro de los errores.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 300  # la subida del vídeo tarda

# Monedas sin subunidad: la API espera la cifra tal cual, no céntimos.
# https://developers.facebook.com/docs/marketing-api/currencies
ZERO_DECIMAL = {
    "CLP", "JPY", "KRW", "VND", "ISK", "HUF", "TWD",
    "COP", "PYG", "UGX", "RWF", "XAF", "XOF", "XPF", "DJF", "GNF",
    "KMF", "MGA", "VUV",
}


def _env_file() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> None:
    if load_dotenv is not None:
        env = _env_file()
        if env.exists():
            load_dotenv(env)


def _need(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(
            f"Falta {name}. Definilo en {_env_file()} o exportalo en el entorno."
        )
    return val


def _scrub(text: str, token: str) -> str:
    """El token nunca debe llegar a stdout ni a un log."""
    return text.replace(token, "<TOKEN>") if token else text


def _post(path: str, token: str, data: dict, files: dict | None = None) -> dict:
    payload = dict(data)
    payload["access_token"] = token
    try:
        r = httpx.post(f"{GRAPH}/{path}", data=payload, files=files, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        sys.exit(f"Fallo de red llamando a {path}: {_scrub(str(exc), token)}")
    if r.status_code >= 400:
        sys.exit(f"Meta rechazó {path} ({r.status_code}):\n{_scrub(r.text, token)}")
    return r.json()


def _get(path: str, token: str, params: dict | None = None) -> dict:
    query = dict(params or {})
    query["access_token"] = token
    try:
        r = httpx.get(f"{GRAPH}/{path}", params=query, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        sys.exit(f"Fallo de red leyendo {path}: {_scrub(str(exc), token)}")
    if r.status_code >= 400:
        sys.exit(f"Meta rechazó leer {path} ({r.status_code}):\n{_scrub(r.text, token)}")
    return r.json()


def account_facts(act: str, token: str) -> dict:
    """Moneda, estado y nombre de la cuenta. La moneda decide el presupuesto."""
    return _get(
        act,
        token,
        {"fields": "name,currency,account_status,timezone_name,disable_reason"},
    )


def budget_minor_units(amount: float, currency: str) -> int:
    """Convierte un importe en unidades enteras al formato que espera la API."""
    if currency in ZERO_DECIMAL:
        return int(round(amount))
    return int(round(amount * 100))


def upload_video(act: str, token: str, video: Path) -> str:
    print(f"Subiendo {video.name} ({video.stat().st_size / 1e6:.1f} MB)…")
    with video.open("rb") as fh:
        out = _post(
            f"{act}/advideos",
            token,
            {"name": video.stem},
            files={"source": (video.name, fh, "video/mp4")},
        )
    vid = out["id"]
    print(f"  vídeo {vid} subido, esperando a que Meta lo procese…")
    return vid


def wait_for_video(video_id: str, token: str, timeout_s: int = 600) -> None:
    """Una creatividad sobre un vídeo aún en proceso falla. Hay que esperar."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        info = _get(video_id, token, {"fields": "status"})
        state = (info.get("status") or {}).get("video_status", "")
        if state == "ready":
            print("  procesado.")
            return
        if state == "error":
            sys.exit(f"Meta no pudo procesar el vídeo: {json.dumps(info)}")
        time.sleep(5)
    sys.exit(f"El vídeo {video_id} sigue procesándose tras {timeout_s}s.")


def pick_thumbnail(video_id: str, token: str) -> str:
    """Una creatividad de vídeo necesita miniatura; Meta genera varias."""
    thumbs = _get(video_id, token, {"fields": "thumbnails"}).get("thumbnails", {})
    items = thumbs.get("data", [])
    if not items:
        sys.exit(f"El vídeo {video_id} no expone miniaturas todavía.")
    preferred = next((t for t in items if t.get("is_preferred")), items[0])
    return preferred["uri"]


def build_spec(args, page_id: str, currency: str) -> dict:
    """Todo lo que se enviará, en un solo sitio, para poder revisarlo en seco."""
    return {
        "campaign": {
            "name": args.name,
            "objective": "OUTCOME_TRAFFIC",
            "status": "PAUSED",
            "special_ad_categories": json.dumps([]),
            # CBO: el presupuesto vive en la campaña, no en el ad set.
            "daily_budget": budget_minor_units(args.daily_budget, currency),
        },
        "adset": {
            "name": f"{args.name} — {args.country}",
            "status": "PAUSED",
            "billing_event": "IMPRESSIONS",
            # Cuenta a quien carga la página, no a quien hace clic y se va.
            "optimization_goal": "LANDING_PAGE_VIEWS",
            # Sin promoted_object: en OUTCOME_TRAFFIC la API lo rechaza
            # (error_subcode 1885014). Vuelve a hacer falta en OFFSITE_CONVERSIONS.
            "targeting": json.dumps(
                {
                    "geo_locations": {"countries": [args.country]},
                    "genders": [2],  # 1 hombres, 2 mujeres
                    "age_min": args.age_min,
                    "age_max": args.age_max,
                }
            ),
        },
        "creative": {
            "name": f"{args.name} — vídeo",
            "page_id": page_id,
            "message": args.message,
            "title": args.headline,
            "link_description": args.description,
            "link": args.link,
            "cta": "SHOP_NOW",
        },
    }


def main() -> None:
    _load_env()

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--account", required=True, help="ID de la cuenta, sin el prefijo act_")
    p.add_argument("--link", required=True, help="URL de destino del anuncio")
    p.add_argument("--video", required=True, help="Ruta local al .mp4")
    p.add_argument("--daily-budget", type=float, required=True,
                   help="Presupuesto diario en unidades enteras de la moneda de la cuenta")
    p.add_argument("--country", default="GB", help="Código ISO del país objetivo (por defecto GB)")
    p.add_argument("--age-min", type=int, default=25)
    p.add_argument("--age-max", type=int, default=54)
    p.add_argument("--name", default="TBW — Butterfly Metal Bookmark")
    p.add_argument("--message", default=(
        "A bookmark that looks like it belongs in the book.\n\n"
        "Cut from metal, thin enough to close the cover on it, and heavy enough "
        "that it doesn't wander out of the page in a bag.\n\n"
        "Four designs. Shipping is priced per destination and the real delivery "
        "estimate shows before you buy."
    ))
    p.add_argument("--headline", default="Butterfly Metal Bookmark — $8.99")
    p.add_argument("--description", default="Four designs. Pick one, or keep the set.")
    p.add_argument("--dry-run", action="store_true", help="Muestra el plan y no llama a Meta")
    args = p.parse_args()

    act = f"act_{args.account}"
    video = Path(args.video)

    if not args.dry_run and not video.is_file():
        sys.exit(
            f"No existe el vídeo: {video}\n"
            "Ejecutá este script en la máquina donde está el archivo."
        )

    token = _need("META_ADS_TOKEN")
    page_id = _need("FB_PAGE_ID")

    # La moneda decide cómo se interpreta el presupuesto. Sin esto, el importe
    # puede salir 100x mayor de lo previsto.
    if args.dry_run:
        currency = os.environ.get("META_ADS_ASSUMED_CURRENCY", "USD")
        print(f"[dry-run] Asumiendo moneda {currency} (la real se consulta al ejecutar).")
        acct = {"name": "(sin consultar)", "account_status": "?"}
    else:
        acct = account_facts(act, token)
        currency = acct.get("currency", "")
        if not currency:
            sys.exit("Meta no devolvió la moneda de la cuenta; abortando por seguridad.")

    minor = budget_minor_units(args.daily_budget, currency)
    print(f"\nCuenta {act} — {acct.get('name')} | moneda {currency} | estado {acct.get('account_status')}")
    print(f"Presupuesto diario: {args.daily_budget:g} {currency} → daily_budget={minor}")
    if acct.get("account_status") not in (1, "?", None):
        print(f"  AVISO: account_status={acct.get('account_status')} no es 1 (activa). "
              f"disable_reason={acct.get('disable_reason')}")

    spec = build_spec(args, page_id, currency)

    if args.dry_run:
        print("\n--- se enviaría ---")
        print(json.dumps(spec, indent=2, ensure_ascii=False))
        print("\nNada se creó. Quitá --dry-run para ejecutarlo.")
        return

    video_id = upload_video(act, token, video)
    wait_for_video(video_id, token)
    thumb = pick_thumbnail(video_id, token)

    creative = _post(f"{act}/adcreatives", token, {
        "name": spec["creative"]["name"],
        "object_story_spec": json.dumps({
            "page_id": page_id,
            "video_data": {
                "video_id": video_id,
                "message": spec["creative"]["message"],
                "title": spec["creative"]["title"],
                "link_description": spec["creative"]["description"],
                "image_url": thumb,
                "call_to_action": {
                    "type": "SHOP_NOW",
                    "value": {"link": args.link},
                },
            },
        }),
        "degrees_of_freedom_spec": json.dumps(
            {"creative_features_spec": {"standard_enhancements": {"enroll_status": "OPT_OUT"}}}
        ),
    })
    print(f"Creatividad {creative['id']}")

    campaign = _post(f"{act}/campaigns", token, spec["campaign"])
    print(f"Campaña {campaign['id']} (PAUSED)")

    adset = _post(f"{act}/adsets", token, {**spec["adset"], "campaign_id": campaign["id"]})
    print(f"Ad set {adset['id']} (PAUSED)")

    ad = _post(f"{act}/ads", token, {
        "name": spec["campaign"]["name"],
        "adset_id": adset["id"],
        "creative": json.dumps({"creative_id": creative["id"]}),
        "status": "PAUSED",
    })
    print(f"Anuncio {ad['id']} (PAUSED)")

    print("\nTodo creado en PAUSED. Nada gasta hasta activarlo a mano.")
    print(json.dumps({
        "campaign": campaign["id"],
        "adset": adset["id"],
        "creative": creative["id"],
        "ad": ad["id"],
        "video": video_id,
    }, indent=2))


if __name__ == "__main__":
    main()
