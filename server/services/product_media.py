"""Append product images on the VPS; preserve originals and the product hero."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import warnings
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError
from sqlalchemy import update

from models import Product

MAX_BYTES = 8 * 1024 * 1024
MAX_IMAGES = 24
MAX_BATCH = 3
PREFIX = "/assets/products/uploads/"
FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


class MediaError(ValueError):
    pass


def public_dir() -> Path:
    default = Path(__file__).resolve().parents[2] / "assets/products/uploads"
    return Path(os.getenv("TBW_PRODUCT_MEDIA_DIR", str(default)))


def private_dir() -> Path:
    return Path(os.getenv("TBW_PRODUCT_MEDIA_PRIVATE_DIR", "/var/lib/tbw-product-media"))


def revision(product: Product) -> str:
    value = json.dumps([product.id, product.image_url, product.gallery_json], ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def gallery(product: Product) -> list[str]:
    try:
        values = json.loads(product.gallery_json or "[]")
    except (ValueError, TypeError):
        raise MediaError("La galería existente no es válida; no se ha cambiado.")
    if not isinstance(values, list) or any(not isinstance(u, str) for u in values):
        raise MediaError("La galería existente no es válida; no se ha cambiado.")
    for url in [product.image_url, *values]:
        if not url:
            continue
        parts = urlsplit(url)
        if not ((parts.scheme in ("http", "https") and parts.netloc)
                or (url.startswith("/") and not url.startswith("//") and not parts.scheme)):
            raise MediaError("La galería contiene una dirección de imagen no válida.")
    # Keep the real hero first, including products whose legacy gallery omitted it.
    return list(dict.fromkeys(u for u in [product.image_url, *values] if u))


def validate_image(data: bytes) -> str:
    if not data or len(data) > MAX_BYTES:
        raise MediaError("Cada imagen debe tener entre 1 byte y 8 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                ext = FORMATS.get(image.format)
                if not ext or getattr(image, "n_frames", 1) != 1:
                    raise MediaError("Solo se admiten imágenes PNG, JPEG o WebP estáticas.")
                if image.width < 100 or image.height < 100 or image.width * image.height > 24_000_000:
                    raise MediaError("La imagen debe medir al menos 100 × 100 y como máximo 24 megapíxeles.")
                image.verify()
            # verify() alone does not decode every format's pixel data.
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        return ext
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, ValueError) as exc:
        if isinstance(exc, MediaError):
            raise
        raise MediaError("El archivo no contiene una imagen válida.") from exc


def _private_json(value: dict) -> None:
    folder = private_dir()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(8) + ".json")
    with path.open("x", encoding="utf-8") as out:
        os.chmod(path, 0o600)
        json.dump(value, out, ensure_ascii=False, indent=2)


def _save_image(product_id: int, data: bytes, ext: str) -> str:
    digest = hashlib.sha256(data).hexdigest()
    folder = public_dir() / str(product_id)
    folder.mkdir(parents=True, exist_ok=True, mode=0o755)
    path = folder / f"{digest}.{ext}"
    # Exclusive creation prevents an upload from replacing existing public bytes.
    temporary = folder / (".upload-" + secrets.token_hex(16))
    try:
        with temporary.open("xb") as out:
            out.write(data)
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise MediaError("El archivo existente no coincide; no se ha cambiado la galería.")
    finally:
        temporary.unlink(missing_ok=True)
    return f"{PREFIX}{product_id}/{digest}.{ext}"


def _change(db, product: Product, expected: str, urls: list[str], *, action: str, origin: str):
    if not expected or not secrets.compare_digest(expected, revision(product)):
        raise MediaError("La galería cambió. Recarga la página antes de continuar.")
    previous = gallery(product)
    if urls == previous:
        return False
    if len(urls) > MAX_IMAGES:
        raise MediaError("La galería admite un máximo de 24 imágenes.")
    before = product.gallery_json
    after = json.dumps(urls, ensure_ascii=False)
    _private_json({"product_id": product.id, "action": action, "origin": origin,
                   "image_url": product.image_url, "before_gallery_json": before,
                   "after_gallery_json": after, "revision": expected})
    # Compare-and-set protects against another tab or process editing after the read.
    result = db.execute(update(Product).where(Product.id == product.id,
        Product.image_url == product.image_url, Product.gallery_json == before)
        .values(gallery_json=after).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise MediaError("La galería cambió. Recarga la página antes de continuar.")
    db.commit()
    db.refresh(product)
    return True


def append(db, product: Product, expected: str, files: list[bytes], *, origin: str, disclosed: bool):
    if origin not in ("real", "ai"):
        raise MediaError("Selecciona el tipo de imagen.")
    if origin == "ai" and not disclosed:
        raise MediaError("Confirma que cada imagen de IA lleva el aviso visible integrado.")
    if not 1 <= len(files) <= MAX_BATCH:
        raise MediaError("Añade entre una y tres imágenes cada vez.")
    if not expected or not secrets.compare_digest(expected, revision(product)):
        raise MediaError("La galería cambió. Recarga la página antes de continuar.")
    extensions = [validate_image(data) for data in files]
    current = gallery(product)
    paths = [f"{PREFIX}{product.id}/{hashlib.sha256(data).hexdigest()}.{ext}"
             for data, ext in zip(files, extensions)]
    merged = list(dict.fromkeys([*current, *paths]))
    if len(merged) > MAX_IMAGES:
        raise MediaError("La galería admite un máximo de 24 imágenes.")
    for data, ext in zip(files, extensions):
        _save_image(product.id, data, ext)
    return _change(db, product, expected, merged, action="append", origin=origin)


def remove(db, product: Product, expected: str, url: str):
    # Removal only unlinks uploads from this product; it never deletes bytes.
    pattern = rf"{re.escape(PREFIX)}{product.id}/[a-f0-9]{{64}}\.(png|jpg|webp)"
    if not re.fullmatch(pattern, url) or url == product.image_url:
        raise MediaError("Solo puedes quitar imágenes adicionales subidas desde este panel.")
    current = gallery(product)
    return _change(db, product, expected, [u for u in current if u != url], action="remove", origin="")
