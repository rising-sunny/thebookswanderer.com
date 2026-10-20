"""Install the isolated admin API. Never loads provider credentials."""
import argparse
import getpass
import hashlib
import json
import os
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
args = parser.parse_args()

service = "tbw-admin-api.service"
source = Path(__file__).resolve().parent / "app.py"
code = Path("/opt/tbw-admin-api")
key = Path("/etc/tbw-admin-api/key")
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

if os.geteuid() != 0:
    raise SystemExit("Ejecutar como root.")
for path in (code, key.parent, unit, snippet):
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
    "note": "No provider credentials or store database backups copied.",
}, indent=2))

site_changed = False
service_created = False
nginx_changed = False

try:
    code.mkdir(mode=0o755)
    shutil.copyfile(source, code / "app.py")
    os.chmod(code / "app.py", 0o644)
    key.parent.mkdir(mode=0o700)
    fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(secret + "\n")

    unit.write_text(
        "[Unit]\n"
        "Description=TBW restricted administrative API\n"
        "After=network.target\n\n"
        "[Service]\n"
        "User=www-data\nGroup=www-data\n"
        "WorkingDirectory=/opt/tbw-admin-api\n"
        "ExecStart=" + str(python) +
        " -m uvicorn app:app --host 127.0.0.1 --port 8878 --workers 1 --no-access-log\n"
        "LoadCredential=admin_key:/etc/tbw-admin-api/key\n"
        "StateDirectory=tbw-admin-api\nStateDirectoryMode=0700\n"
        "Environment=TBW_ADMIN_DRAFT_DB=/var/lib/tbw-admin-api/drafts.sqlite3\n"
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
            or health.get("product_publication_enabled") is not False
        ):
            raise RuntimeError("Capacidades administrativas inesperadas.")

        products = client.get(
            "http://127.0.0.1:8878/products?limit=1", headers=headers
        )
        if products.status_code != 200:
            raise RuntimeError("No se pudo leer el catálogo en modo protegido.")
        drafts = client.get(
            "http://127.0.0.1:8878/drafts?limit=1", headers=headers
        )
        if drafts.status_code != 200:
            raise RuntimeError("No se pudo acceder al registro de borradores.")

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
        response = client.get(url, headers=headers)
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
    print("Catálogo: lectura correcta. Registro de borradores: accesible.")
    print("Pedidos reales y publicación: deshabilitados.")
    print("No se creó ningún borrador ni se reinició la tienda.")
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
