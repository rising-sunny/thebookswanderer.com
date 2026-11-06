#!/usr/bin/env python3
"""Publish one approved Reading Society image to Facebook and Instagram.

Dry run by default. Credentials remain on the VPS. A durable journal blocks
automatic retries after an uncertain write; it never runs the daily reel job.
"""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urljoin, urlsplit

import httpx
from dotenv import dotenv_values
from PIL import Image

STORE = "https://thebookswanderer.com"
GRAPH = "https://graph.facebook.com/v21.0"
PAGE = "1200587819810293"
INSTAGRAM = "17841443635177157"
CAMPAIGN = "reading_society_tote_photo_20261019"
SLUG = "reading-society-tote"
TEXT = ("Good books. Long conversations.\n\n"
        "Meet The Reading Society tote. Make a little room for the paperback "
        "that goes everywhere with you.\n\nWhat are you reading lately?")
FB_TEXT = TEXT + "\n\n" + STORE + "/products/" + SLUG
IG_TEXT = TEXT + ("\n\nExplore via the link in our bio.\n\n"
                  "#TheBooksWanderer #TheReadingSociety #BookLovers #ReadingLife")


class SafeError(Exception):
    pass


def owned_url(value):
    if not isinstance(value, str) or not value.strip():
        raise SafeError("El producto no tiene una imagen pública.")
    url = urljoin(STORE + "/", value)
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "thebookswanderer.com"
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment):
        raise SafeError("La imagen debe ser una URL HTTPS de la tienda sin parámetros.")
    return url


def preflight(client):
    response = client.get(STORE + "/api/products/by-slug/" + SLUG)
    if response.status_code != 200:
        raise SafeError(f"Producto no disponible: HTTP {response.status_code}.")
    product = response.json()
    if not isinstance(product, dict):
        raise SafeError("Respuesta de producto no válida.")
    title = str(product.get("title") or product.get("name") or "")
    if "tote" not in title.lower() or "reading society" not in title.lower():
        raise SafeError("El producto actual no coincide con la tote Reading Society.")
    image_url = owned_url(product.get("image_url"))
    with client.stream("GET", image_url) as response:
        if response.status_code != 200:
            raise SafeError(f"Imagen no disponible: HTTP {response.status_code}.")
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > 8 * 1024 * 1024:
                raise SafeError("La imagen supera 8 MB.")
    with Image.open(io.BytesIO(content)) as picture:
        width, height = picture.size
        if (picture.format != "JPEG" or not 320 <= width <= 1440
                or not 0.8 <= width / height <= 1.91):
            raise SafeError("La imagen requiere un JPEG de 320–1440 px de ancho "
                            "y proporción entre 4:5 y 1.91:1.")
        picture.verify()
    return {"product": title, "image_url": image_url,
            "image_sha256": hashlib.sha256(content).hexdigest(),
            "facebook_caption": FB_TEXT, "instagram_caption": IG_TEXT}


def graph(client, token, method, path, **kwargs):
    response = client.request(method, GRAPH + "/" + path,
                              headers={"Authorization": "Bearer " + token}, **kwargs)
    try:
        data = response.json()
    except ValueError:
        raise SafeError(f"Meta devolvió una respuesta no válida: HTTP {response.status_code}.")
    if response.status_code != 200 or not isinstance(data, dict) or "error" in data:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        raise SafeError(f"Meta: HTTP {response.status_code}; código {error.get('code')}; "
                        f"subcódigo {error.get('error_subcode')}. Detalles ocultos.")
    return data


def save(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=".social-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_once(path, journal, network, operation, action):
    record = journal[network]
    record["state"] = "uncertain"
    record["operation"] = operation
    save(path, journal)
    result = action()
    identifier = result.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise SafeError("Meta no confirmó un ID. No repitas la publicación.")
    return result


def publish(client, token, payload, path, journal):
    for network in ("facebook", "instagram"):
        if journal[network]["state"] == "uncertain":
            raise SafeError(f"Hay una escritura incierta en {network}. "
                            "Conserva el registro; revisaremos Meta antes de repetir.")
    page = graph(client, token, "GET", PAGE,
                 params={"fields": "id,name,instagram_business_account"})
    if (page.get("id") != PAGE
            or page.get("instagram_business_account", {}).get("id") != INSTAGRAM):
        raise SafeError("La página o la cuenta vinculada no coincide.")
    ig = graph(client, token, "GET", INSTAGRAM, params={"fields": "id,username"})
    if ig.get("username") != "thebooks.wanderer":
        raise SafeError("La cuenta Instagram no coincide.")
    fb = journal["facebook"]
    if fb["state"] != "published":
        result = write_once(path, journal, "facebook", "publish_photo", lambda: graph(
            client, token, "POST", PAGE + "/photos", data={
                "url": payload["image_url"], "message": FB_TEXT, "published": "true"}))
        fb.update(state="published", photo_id=result["id"],
                  post_id=result.get("post_id"),
                  url="https://www.facebook.com/" + str(result.get("post_id") or result["id"]))
        save(path, journal)
        print("Facebook: foto publicada. " + fb["url"], flush=True)
    record = journal["instagram"]
    if record["state"] == "published":
        return
    if not record.get("container_id"):
        result = write_once(path, journal, "instagram", "create_image_container", lambda: graph(
            client, token, "POST", INSTAGRAM + "/media", data={
                "image_url": payload["image_url"], "caption": IG_TEXT}))
        record.update(state="container_created", container_id=result["id"])
        save(path, journal)
    for _ in range(10):
        status = graph(client, token, "GET", record["container_id"],
                       params={"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED", "PUBLISHED"):
            raise SafeError(f"Contenedor Instagram: {status}. Conserva el registro para revisión.")
        time.sleep(3)
    else:
        raise SafeError("Instagram sigue procesando la foto. Puedes repetir el mismo comando: "
                        "reutilizará el contenedor y omitirá Facebook.")
    result = write_once(path, journal, "instagram", "publish_image", lambda: graph(
        client, token, "POST", INSTAGRAM + "/media_publish",
        data={"creation_id": record["container_id"]}))
    record.update(state="published", media_id=result["id"])
    save(path, journal)
    print("Instagram: imagen publicada. ID: " + result["id"], flush=True)
    # Publication is already persisted even if this optional permalink lookup fails.
    try:
        info = graph(client, token, "GET", result["id"], params={"fields": "permalink,media_type"})
        record.update(url=info.get("permalink"), media_type=info.get("media_type"))
        save(path, journal)
    except (SafeError, httpx.HTTPError):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--server-root", type=Path,
                        default=Path("/var/www/thebookswanderer.com/server"))
    args = parser.parse_args()
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        if not args.publish:
            print(json.dumps({"mode": "preview", **preflight(client)}, ensure_ascii=False, indent=2))
            return
        env = dotenv_values(args.server_root / ".env")
        token = (env.get("FB_PAGE_TOKEN") or "").strip()
        if (env.get("FB_PAGE_ID") or "").strip() != PAGE or not token:
            raise SafeError("Faltan credenciales de la página esperada en .env.")
        directory = args.server_root / "data" / "static-social-posts"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = os.open(directory / (CAMPAIGN + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(lock, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = directory / (CAMPAIGN + ".json")
            if path.exists():
                journal = json.loads(path.read_text())
            else:
                journal = {"campaign": CAMPAIGN, "payload": preflight(client),
                           "facebook": {"state": "ready"}, "instagram": {"state": "ready"}}
                save(path, journal)
            if not all(journal[key]["state"] == "published" for key in ("facebook", "instagram")):
                fresh = preflight(client)
                if fresh != journal["payload"]:
                    raise SafeError("El producto o la imagen cambió. Revisa el registro antes de publicar.")
                publish(client, token, journal["payload"], path, journal)
            print(json.dumps({key: journal[key] for key in ("campaign", "facebook", "instagram")},
                             ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Interrumpido. Conserva el registro antes de repetir.")
    except Exception as exc:
        message = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        raise SystemExit("Publicación detenida: " + message + "\nNo borres el registro de publicación.")
