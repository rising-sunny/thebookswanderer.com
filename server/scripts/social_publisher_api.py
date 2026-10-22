"""Private HTTPS photo publisher; run with one uvicorn worker behind nginx."""
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import secrets

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from dotenv import dotenv_values

ROOT = Path(os.environ.get("TBW_SERVER_ROOT", "/var/www/thebookswanderer.com/server"))
DATA = Path(os.environ.get("TBW_SOCIAL_DATA", "/var/lib/tbw-social-publisher"))
KEY = Path(os.environ.get("TBW_SOCIAL_KEY_FILE", "/etc/tbw-social-publisher/key"))
CORE = Path(__file__).with_name("static_social_post.py")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.on_event("startup")
def reconcile_interrupted_jobs():
    # A restart never resubmits a write whose outcome could be unknown.
    for path in DATA.glob("*.json"):
        record = json.loads(path.read_text())
        if record.get("job") == "publishing":
            record["job"] = "review_required"
            record["error"] = "ServiceInterrupted"
            core().save(path, record)


def core():
    # Each request gets its own namespace; no shared caption or campaign globals.
    spec = importlib.util.spec_from_file_location("private_photo_core", CORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def authorize(request: Request):
    try:
        key = KEY.read_text().strip()
    except OSError:
        raise HTTPException(503, "Publicador no configurado")
    supplied = request.headers.get("authorization", "")
    if len(key) < 32 or not secrets.compare_digest(supplied.encode(), ("Bearer " + key).encode()):
        raise HTTPException(401, "No autorizado")


def credentials():
    env = dotenv_values(Path(os.environ.get("TBW_SOCIAL_META_ENV", str(ROOT / ".env"))))
    token = (env.get("FB_PAGE_TOKEN") or "").strip()
    if not token or (env.get("FB_PAGE_ID") or "").strip() != core().PAGE:
        raise HTTPException(503, "Faltan credenciales Meta de la página esperada")
    return token


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,79}$")
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,119}$")
    facebook_caption: str = Field(min_length=1, max_length=2000)
    instagram_caption: str = Field(min_length=1, max_length=2200)


def journal_path(campaign):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,79}", campaign):
        raise HTTPException(422, "Referencia no válida")
    return DATA / (campaign + ".json")


def image_preflight(client, draft, module):
    response = client.get(module.STORE + "/api/products/by-slug/" + draft.slug)
    if response.status_code != 200:
        raise ValueError("Producto no disponible")
    product = response.json()
    if not isinstance(product, dict) or not (product.get("name") or product.get("title")):
        raise ValueError("Producto no válido")
    url = module.owned_url(product.get("image_url"))
    content = bytearray()
    with client.stream("GET", url) as image:
        if image.status_code != 200:
            raise ValueError("Imagen no disponible")
        for chunk in image.iter_bytes():
            content.extend(chunk)
            if len(content) > 8 * 1024 * 1024:
                raise ValueError("Imagen mayor de 8 MB")
    with Image.open(io.BytesIO(content)) as picture:
        width, height = picture.size
        if picture.format != "JPEG" or not 320 <= width <= 1440 or not 0.8 <= width / height <= 1.91:
            raise ValueError("Se requiere JPEG compatible con Instagram; no se modifica la imagen")
        picture.verify()
    return {"product": product.get("name") or product.get("title"), "image_url": url,
            "image_sha256": hashlib.sha256(content).hexdigest(),
            "facebook_caption": draft.facebook_caption, "instagram_caption": draft.instagram_caption}


@app.get("/health", dependencies=[Depends(authorize)])
def health():
    credentials()
    return {"service": "tbw-social-publisher", "ready": True, "format": "photo",
            "networks": ["facebook", "instagram"], "publishes_on_health_check": False}


@app.post("/drafts", dependencies=[Depends(authorize)])
def create_draft(draft: Draft):
    module = core()
    path = journal_path(draft.campaign)
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(DATA / ".drafts.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            previous = json.loads(path.read_text())
            if previous["request"] != draft.model_dump():
                raise HTTPException(409, "La referencia ya tiene otro contenido")
            return previous
        try:
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                payload = image_preflight(client, draft, module)
        except Exception:
            raise HTTPException(422, "No se pudo validar el producto y su JPEG público. No se publicó nada.")
        record = {"campaign": draft.campaign, "request": draft.model_dump(), "payload": payload,
                  "job": "draft", "facebook": {"state": "ready"}, "instagram": {"state": "ready"}}
        module.save(path, record)
        return record


@app.get("/jobs/{campaign}", dependencies=[Depends(authorize)])
def status(campaign: str):
    path = journal_path(campaign)
    if not path.exists():
        raise HTTPException(404, "Referencia no encontrada")
    return json.loads(path.read_text())


def run_job(campaign):
    path = journal_path(campaign)
    module = core()
    journal = json.loads(path.read_text())
    draft = Draft(**journal["request"])
    module.FB_TEXT = draft.facebook_caption
    module.IG_TEXT = draft.instagram_caption
    try:
        token = credentials()
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            fresh = image_preflight(client, draft, module)
            if fresh != journal["payload"]:
                raise ValueError("El producto o la imagen cambió desde la preparación")
            module.publish(client, token, journal["payload"], path, journal)
        journal["job"] = "published"
    except Exception as exc:
        journal["job"] = "review_required"
        journal["error"] = type(exc).__name__
    module.save(path, journal)


@app.post("/jobs/{campaign}/publish", dependencies=[Depends(authorize)])
def submit(campaign: str, tasks: BackgroundTasks):
    path = journal_path(campaign)
    descriptor = os.open(DATA / ".submit.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            raise HTTPException(404, "Prepara el borrador antes de publicar")
        journal = json.loads(path.read_text())
        if journal["job"] != "draft":
            return journal
        credentials()
        journal["job"] = "publishing"
        core().save(path, journal)
        tasks.add_task(run_job, campaign)
        return JSONResponse({"campaign": campaign, "job": "publishing",
                             "status_path": "/jobs/" + campaign}, status_code=202)
