"""Install or upgrade the isolated admin API. It receives the CJ and draft keys."""
import argparse
import getpass
import grp
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
parser.add_argument("--resume", action="store_true")
parser.add_argument("--upgrade", action="store_true")
args = parser.parse_args()

service = "tbw-admin-api.service"
source = Path(__file__).resolve().parent / "app.py"
code = Path("/opt/tbw-admin-api")
key = Path("/etc/tbw-admin-api/key")
cj_key = Path("/etc/tbw-admin-api/cj_api_key")
store_env = Path("/var/www/thebookswanderer.com/server/.env")
cj_line = "LoadCredential=cj_api_key:/etc/tbw-admin-api/cj_api_key\n"
draft_key = Path("/etc/thebookswanderer/draft_key")
draft_line = "LoadCredential=draft_key:/etc/thebookswanderer/draft_key\n"
unit = Path("/etc/systemd/system") / service
snippet = Path("/etc/nginx/snippets/tbw-admin-api.conf")
site = Path("/etc/nginx/sites-available/thebookswanderer.com")
python = Path("/var/www/thebookswanderer.com/server/.venv/bin/python")
anchor = "include /etc/nginx/snippets/tbw-social-publisher.conf;"

def command(*values):
    result = subprocess.run(values, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Falló: " + " ".join(values[:2]))
    return result.stdout.strip()

def ensure_cj_key():
    """Copy CJ_API_KEY from the store .env into a root-only credential file."""
    if cj_key.exists():
        if cj_key.stat().st_uid != 0 or cj_key.stat().st_mode & 0o077:
            raise SystemExit("La clave CJ no tiene propietario o permisos seguros.")
        return
    values = [
        line.split("=", 1)[1].strip().strip("'\"")
        for line in store_env.read_text().splitlines()
        if line.startswith("CJ_API_KEY=")
    ]
    if len(values) != 1 or not values[0]:
        raise SystemExit("No se encontró un único CJ_API_KEY en el .env de la tienda.")
    fd = os.open(cj_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(values[0] + "\n")

def ensure_draft_key():
    """Key shared with the store (group www-data), which reads it per request."""
    group = grp.getgrnam("www-data").gr_gid
    if not draft_key.parent.exists():
        draft_key.parent.mkdir()
        os.chown(draft_key.parent, 0, group)
        os.chmod(draft_key.parent, 0o750)
    if draft_key.exists():
        if draft_key.stat().st_uid != 0 or draft_key.stat().st_mode & 0o037:
            raise SystemExit("La clave de borradores no tiene propietario o permisos seguros.")
        return
    fd = os.open(draft_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(secrets.token_urlsafe(48) + "\n")
    os.chown(draft_key, 0, group)
    os.chmod(draft_key, 0o640)

def store_has_drafts():
    """The deployed store answers its draft routes (422 on an invalid body)."""
    try:
        return all(
            httpx.post("http://127.0.0.1:8010/api/internal" + path,
                       json=[], timeout=10).status_code == 422
            for path in ("/drafts", "/drafts/1/update", "/drafts/1/publish",
                         "/products/1/unpublish", "/shipping/1",
                         "/suppliers/printify/products", "/suppliers/cj/api")
        )
    except httpx.HTTPError:
        return False

def wait_health(secret):
    headers = {"Authorization": "Bearer " + secret}
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        for attempt in range(20):
            try:
                response = client.get("http://127.0.0.1:8878/health", headers=headers)
                if response.status_code == 200:
                    break
            except httpx.RequestError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("El servicio administrativo no respondió.")
        if client.get("http://127.0.0.1:8878/health").status_code != 401:
            raise RuntimeError("La comprobación sin clave no fue rechazada.")
    return response.json()

if os.geteuid() != 0:
    raise SystemExit("Ejecutar como root.")
if args.upgrade:
    for path in (unit, code / "app.py", key):
        if not path.is_file():
            raise SystemExit("No hay instalación que actualizar: falta " + str(path))
    if key.stat().st_uid != 0 or key.stat().st_mode & 0o077:
        raise SystemExit("La clave no tiene propietario o permisos seguros.")
    compile(source.read_text(), str(source), "exec")
    unit_before = unit.read_text()
    if "LoadCredential=admin_key:" not in unit_before:
        raise SystemExit("La unidad instalada no tiene el formato esperado.")
    if not store_has_drafts():
        raise SystemExit("La tienda desplegada aún no tiene borradores; despliega main primero.")
    if args.check:
        print("Precomprobación de actualización correcta.")
        raise SystemExit(0)
    ensure_cj_key()
    ensure_draft_key()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = Path("/var/backups/tbw-admin-api") / timestamp
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(code / "app.py", backup / "app.py.before")
    shutil.copy2(unit, backup / "unit.before")
    try:
        shutil.copyfile(source, code / "app.py")
        unit_after = unit_before
        for line in (cj_line, draft_line):
            if line not in unit_after:
                unit_after = unit_after.replace(
                    "LoadCredential=admin_key:", line + "LoadCredential=admin_key:", 1
                )
        if unit_after != unit_before:
            unit.write_text(unit_after)
        command("systemctl", "daemon-reload")
        command("systemctl", "restart", service)
        health = wait_health(key.read_text().strip())
        if (
            not {"cj:read", "products:draft", "products:publish"}
            <= set(health.get("capabilities", []))
            or health.get("order_submission_enabled") is not False
        ):
            raise RuntimeError("Capacidades administrativas inesperadas.")
    except Exception as error:
        shutil.copyfile(backup / "app.py.before", code / "app.py")
        shutil.copyfile(backup / "unit.before", unit)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        subprocess.run(["systemctl", "restart", service], capture_output=True)
        print("Actualización revertida:", type(error).__name__)
        if isinstance(error, RuntimeError):
            print(str(error))
        print("Respaldo:", backup)
        raise SystemExit(1)
    print("API administrativa actualizada: catálogo, CJ, borradores y publicación con código.")
    print("Pedidos reales: deshabilitados. Tienda no reiniciada.")
    print("Respaldo:", backup)
    raise SystemExit(0)
if args.resume:
    if not key.is_file() or not (code / "app.py").is_file():
        raise SystemExit("Falta la instalación parcial o su clave.")
    if key.stat().st_uid != 0 or key.stat().st_mode & 0o077:
        raise SystemExit("La clave no tiene propietario o permisos seguros.")
    if source.read_bytes() != (code / "app.py").read_bytes():
        raise SystemExit("El código parcial no coincide; revisar antes.")
for path in ((unit, snippet) if args.resume else (code, key.parent, unit, snippet)):
    if path.exists():
        raise SystemExit("Ya existe " + str(path) + "; no se sobrescribirá.")
if not source.is_file() or not python.is_file():
    raise SystemExit("Falta el código o el Python de la tienda.")
original = site.read_bytes()
original_text = original.decode()
if original_text.count(anchor) != 1:
    raise SystemExit("No se encontró un único punto de inclusión Nginx.")
if "/api/ops/" in original_text or "tbw-admin-api" in original_text:
    raise SystemExit("Ya existe una configuración administrativa; revisar antes.")
command("nginx", "-t")
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 8878))
compile(source.read_text(), str(source), "exec")

if args.check:
    print("Precomprobación correcta: archivos nuevos, puerto libre y Nginx válido.")
    raise SystemExit(0)

if args.resume:
    secret = key.read_text().strip()
    confirmation = secret
else:
    secret = getpass.getpass("Nueva clave administrativa (mínimo 32 caracteres): ")
    confirmation = getpass.getpass("Repítela: ")
if (
    len(secret) < 32 or secret != confirmation
    or secret != secret.strip() or not secret.isascii()
    or any(ord(c) < 33 or ord(c) > 126 for c in secret)
    or set(secret) == {"*"}
):
    raise SystemExit("Clave inválida o distinta. No se instaló nada.")

timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
backup = Path("/var/backups/tbw-admin-api") / timestamp
backup.mkdir(parents=True, mode=0o700)
shutil.copy2(site, backup / "nginx-site.before")
(backup / "installation.json").write_text(json.dumps({
    "app_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "service": service,
    "note": "No credentials or store database backups copied.",
}, indent=2))

site_changed = False
service_created = False
nginx_changed = False

try:
    code.mkdir(mode=0o755, exist_ok=args.resume)
    shutil.copyfile(source, code / "app.py")
    os.chmod(code / "app.py", 0o644)
    key.parent.mkdir(mode=0o700, exist_ok=args.resume)
    if not args.resume:
        fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(secret + "\n")
    ensure_cj_key()
    ensure_draft_key()

    unit.write_text(
        "[Unit]\n"
        "Description=TBW restricted administrative API\n"
        "After=network.target\n\n"
        "[Service]\n"
        "User=www-data\nGroup=www-data\n"
        "WorkingDirectory=/opt/tbw-admin-api\n"
        "ExecStart=" + str(python) +
        " -m uvicorn app:app --host 127.0.0.1 --port 8878 --workers 1 --no-access-log\n"
        + cj_line + draft_line +
        "LoadCredential=admin_key:/etc/tbw-admin-api/key\n"
        "StateDirectory=tbw-admin-api\nStateDirectoryMode=0700\n"
        "Environment=TBW_ADMIN_STORE_DB=/var/www/thebookswanderer.com/server/data/store.db\n"
        "Restart=on-failure\nRestartSec=3\nUMask=0077\n"
        "NoNewPrivileges=yes\nPrivateTmp=yes\n"
        "ProtectSystem=strict\nProtectHome=yes\n"
        "ReadOnlyPaths=/var/www/thebookswanderer.com /opt/tbw-admin-api\n"
        "CapabilityBoundingSet=\n"
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX\n"
        "ProtectKernelTunables=yes\nProtectKernelModules=yes\n"
        "ProtectControlGroups=yes\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    )
    service_created = True
    os.chmod(unit, 0o644)
    command("systemctl", "daemon-reload")
    command("systemctl", "start", service)

    headers = {"Authorization": "Bearer " + secret}
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        for attempt in range(20):
            try:
                response = client.get(
                    "http://127.0.0.1:8878/health", headers=headers
                )
                if response.status_code == 200:
                    break
            except httpx.RequestError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("El servicio administrativo no respondió.")

        if client.get("http://127.0.0.1:8878/health").status_code != 401:
            raise RuntimeError("La comprobación sin clave no fue rechazada.")
        health = response.json()
        if (
            health.get("service") != "tbw-admin-api"
            or health.get("order_submission_enabled") is not False
        ):
            raise RuntimeError("Capacidades administrativas inesperadas.")

        products = client.get(
            "http://127.0.0.1:8878/products?limit=1", headers=headers
        )
        if products.status_code != 200:
            raise RuntimeError("No se pudo leer el catálogo en modo protegido.")

    snippet.write_text(
        "# Managed by deploy/admin-api/install.py\n"
        "location ^~ /api/ops/ {\n"
        "    if ($scheme != https) { return 403; }\n"
        "    client_max_body_size 32k;\n"
        "    proxy_pass http://127.0.0.1:8878/;\n"
        "    proxy_set_header Host $host;\n"
        "    proxy_set_header Authorization $http_authorization;\n"
        "    proxy_set_header X-Forwarded-Proto $scheme;\n"
        "    proxy_read_timeout 30s;\n"
        "    proxy_no_cache 1;\n"
        "    proxy_cache_bypass 1;\n"
        "}\n"
    )
    os.chmod(snippet, 0o644)
    updated = original_text.replace(
        anchor,
        anchor + "\n    include /etc/nginx/snippets/tbw-admin-api.conf;",
        1,
    )
    site_changed = True
    site.write_text(updated)
    command("nginx", "-t")
    nginx_changed = True
    command("systemctl", "reload", "nginx")

    with httpx.Client(timeout=20, follow_redirects=False) as client:
        url = "https://thebookswanderer.com/api/ops/health"
        response = None
        for attempt in range(12):
            try:
                response = client.get(url, headers=headers)
                try:
                    body = response.json()
                except ValueError:
                    body = None
                valid = (
                    response.status_code == 200
                    and isinstance(body, dict)
                    and body.get("service") == "tbw-admin-api"
                    and body.get("order_submission_enabled") is False
                )
                if valid:
                    break
            except httpx.RequestError:
                pass
            time.sleep(2)
        if response is None:
            raise RuntimeError("No se obtuvo respuesta HTTPS durante la espera.")
        try:
            diagnostic = response.json()
        except ValueError:
            diagnostic = None
        print("HTTPS administrativo: HTTP", response.status_code)
        print("Tipo de contenido:", response.headers.get("content-type", "").split(";")[0])
        print("Servicio esperado:", isinstance(diagnostic, dict) and diagnostic.get("service") == "tbw-admin-api")
        if (
            response.status_code != 200
            or response.json().get("service") != "tbw-admin-api"
            or response.json().get("order_submission_enabled") is not False
        ):
            raise RuntimeError("La comprobación HTTPS autenticada no pasó.")
        if client.get(url).status_code != 401:
            raise RuntimeError("HTTPS sin clave no fue rechazado.")
        if client.get(
            "https://thebookswanderer.com/api/health"
        ).status_code != 200:
            raise RuntimeError("La comprobación HTTP de la tienda no pasó.")

    command("systemctl", "enable", service)
    print("Instalado: https://thebookswanderer.com/api/ops/health")
    print("Autenticación local y HTTPS: con clave 200, sin clave 401.")
    print("Catálogo: lectura correcta. CJ: solo lectura.")
    print("Pedidos reales: deshabilitados. Publicación: solo borradores con código.")
    print("No se reinició la tienda.")
    print("Respaldo Nginx:", backup)
except Exception as error:
    failures = []
    if service_created:
        result = subprocess.run(
            ["systemctl", "disable", "--now", service], capture_output=True
        )
        if result.returncode:
            failures.append("detener servicio administrativo")
    if site_changed:
        site.write_bytes(original)
    if snippet.exists():
        snippet.unlink()
    if nginx_changed:
        result = subprocess.run(["nginx", "-t"], capture_output=True)
        if result.returncode == 0:
            result = subprocess.run(
                ["systemctl", "reload", "nginx"], capture_output=True
            )
        if result.returncode:
            failures.append("restaurar Nginx")
    if unit.exists():
        unit.unlink()
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
    print("Instalación incompleta:", type(error).__name__)
    if isinstance(error, RuntimeError):
        print(str(error))
    print("Se conservaron la clave, los datos y el respaldo; no se regeneraron.")
    print("Restauración:", ", ".join(failures) if failures else "sin errores detectados")
    raise SystemExit(1)
