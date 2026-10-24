"""Install or upgrade the owner-only MCP service without rotating credentials."""
import argparse
import json
import os
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx2
from tbw_mcp import BASE_URL, CALLBACK, OWNER_ID, create_app

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
parser.add_argument("--resume", action="store_true")
parser.add_argument("--upgrade", action="store_true")
args = parser.parse_args()

source = Path(__file__).resolve().parent / "tbw_mcp.py"
target = Path("/opt/tbw-mcp/tbw_mcp.py")
unit = Path("/etc/systemd/system/tbw-mcp.service")
snippet = Path("/etc/nginx/snippets/tbw-mcp.conf")
site = Path("/etc/nginx/sites-available/thebookswanderer.com")
oauth_file = Path("/etc/tbw-mcp/oauth.json")
admin_file = Path("/etc/tbw-admin-api/key")
anchor = "include /etc/nginx/snippets/tbw-admin-api.conf;"
service = "tbw-mcp.service"

def command(*values):
    result = subprocess.run(values, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Falló: " + " ".join(values[:2]))
    return result.stdout.strip()

if os.geteuid() != 0:
    raise SystemExit("Ejecutar como root.")
if args.upgrade:
    for path in (unit, snippet, target):
        if not path.is_file():
            raise SystemExit("No hay instalación que actualizar: falta " + str(path))
for path in (() if args.upgrade else (unit, snippet)):
    if path.exists():
        raise SystemExit("Ya existe " + str(path) + "; no se sobrescribirá.")
if args.upgrade:
    pass
elif target.exists():
    if not args.resume or target.read_bytes() != source.read_bytes():
        raise SystemExit("El código instalado ya existe o no coincide; revisar antes.")
elif args.resume:
    raise SystemExit("No se encontró una instalación parcial para reanudar.")

for path in (oauth_file, admin_file):
    if not path.is_file() or path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
        raise SystemExit("Credencial ausente o con permisos inseguros: " + str(path))

config = json.loads(oauth_file.read_text())
if (
    str(config.get("allowed_github_id")) != OWNER_ID
    or config.get("base_url") != BASE_URL
    or config.get("redirect_path") != CALLBACK
):
    raise SystemExit("La configuración OAuth no coincide con la aplicación preparada.")

original = site.read_bytes()
original_text = original.decode()
if original_text.count(anchor) != 1:
    raise SystemExit("No se encontró un único punto de inclusión Nginx.")
if ("tbw-mcp.conf" in original_text) != args.upgrade:
    raise SystemExit("La inclusión MCP de Nginx no coincide con el modo elegido.")

with tempfile.TemporaryDirectory() as temporary:
    fake = {
        "allowed_github_id": OWNER_ID,
        "base_url": BASE_URL,
        "redirect_path": CALLBACK,
        "github_client_id": "offline-client",
        "github_client_secret": "s" * 40,
        "jwt_signing_key": "k" * 64,
    }
    app = create_app(fake, "a" * 40, temporary)
    routes = {getattr(route, "path", "") for route in app.routes}
routes.discard("")
routes.discard("/")
routes.update({"/mcp", "/mcp/"})
for route in routes:
    if not re.fullmatch(r"/[A-Za-z0-9._/-]+", route):
        raise SystemExit("Ruta dinámica no prevista: " + route)
    if args.upgrade:
        if "location = " + route + " {" not in snippet.read_text():
            raise SystemExit("La nueva versión necesita una ruta Nginx no instalada: " + route)
    elif re.search(r"location\s*=\s*" + re.escape(route) + r"\s*\{", original_text):
        raise SystemExit("Ya existe una ruta Nginx: " + route)
if not {"/authorize", "/token", "/register", "/consent", CALLBACK} <= routes:
    raise SystemExit("No se encontraron todas las rutas OAuth necesarias.")

command("nginx", "-t")
if not args.upgrade:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8879))
if command("systemctl", "is-active", "tbw-admin-api.service") != "active":
    raise SystemExit("La API administrativa no está activa.")

if args.check:
    print("Precomprobación correcta. Rutas MCP/OAuth:")
    for route in sorted(routes):
        print(" ", route)
    raise SystemExit(0)

try:
    account = pwd.getpwnam("tbw-mcp")
    if account.pw_uid in {0, pwd.getpwnam("www-data").pw_uid}:
        raise SystemExit("La identidad tbw-mcp no está aislada.")
except KeyError:
    command(
        "useradd", "--system", "--home-dir", "/var/lib/tbw-mcp",
        "--no-create-home", "--shell", "/usr/sbin/nologin", "tbw-mcp",
    )

timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
backup = Path("/var/backups/tbw-mcp") / timestamp
backup.mkdir(parents=True, mode=0o700)
shutil.copy2(site, backup / "nginx-site.before")
changed = None
service_created = False
nginx_reloaded = False

initialize = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "installation-check", "version": "1"},
    },
}

def verify(client, base, local=False):
    headers = {"Host": "thebookswanderer.com"} if local else {}
    response = client.get(
        base + "/.well-known/oauth-authorization-server", headers=headers
    )
    if response.status_code != 200:
        return False
    metadata = response.json()
    if (
        metadata.get("issuer", "").rstrip("/") != BASE_URL
        or "read:user" not in metadata.get("scopes_supported", [])
        or not metadata.get("registration_endpoint")
    ):
        return False
    response = client.post(
        base + "/mcp",
        headers=dict(headers, Accept="application/json, text/event-stream"),
        json=initialize,
    )
    if response.status_code != 401:
        return False
    challenge = response.headers.get("www-authenticate", "")
    match = re.search(r'resource_metadata="([^"]+)"', challenge)
    if not match or not match.group(1).startswith(
        BASE_URL + "/.well-known/oauth-protected-resource"
    ):
        return False
    resource_url = match.group(1)
    if local:
        resource_url = base + resource_url.removeprefix(BASE_URL)
    resource = client.get(resource_url, headers=headers)
    if resource.status_code != 200:
        return False
    data = resource.json()
    return (
        data.get("resource", "").rstrip("/") == BASE_URL + "/mcp"
        and BASE_URL in [
            value.rstrip("/") for value in data.get("authorization_servers", [])
        ]
    )

if args.upgrade:
    shutil.copy2(target, backup / "tbw_mcp.py.before")
    try:
        shutil.copyfile(source, target)
        command("systemctl", "restart", service)
        with httpx2.Client(timeout=15, follow_redirects=False) as client:
            for base, local, attempts in (
                ("http://127.0.0.1:8879", True, 20), (BASE_URL, False, 12),
            ):
                for attempt in range(attempts):
                    try:
                        if verify(client, base, local=local):
                            break
                    except (httpx2.HTTPError, ValueError):
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError("La comprobación MCP/OAuth no pasó: " + base)
    except Exception as error:
        shutil.copyfile(backup / "tbw_mcp.py.before", target)
        subprocess.run(["systemctl", "restart", service], capture_output=True)
        print("Actualización revertida:", type(error).__name__)
        if isinstance(error, RuntimeError):
            print(str(error))
        print("Respaldo:", backup)
        raise SystemExit(1)
    print("MCP actualizado:", BASE_URL + "/mcp")
    print("Herramientas: salud, catálogo, CJ, borradores y publicación con código. Sin pedidos.")
    print("Clientes OAuth: ChatGPT, Claude y CLI en loopback.")
    print("Respaldo:", backup)
    raise SystemExit(0)

try:
    shutil.copyfile(source, target)
    os.chmod(target, 0o644)
    unit.write_text(
        "[Unit]\nDescription=TBW owner-only OAuth MCP bridge\n"
        "After=network-online.target tbw-admin-api.service\n"
        "Wants=network-online.target\n\n"
        "[Service]\nUser=tbw-mcp\nGroup=tbw-mcp\n"
        "WorkingDirectory=/opt/tbw-mcp\n"
        "ExecStart=/opt/tbw-mcp/.venv/bin/python /opt/tbw-mcp/tbw_mcp.py\n"
        "LoadCredential=oauth_config:/etc/tbw-mcp/oauth.json\n"
        "LoadCredential=admin_key:/etc/tbw-admin-api/key\n"
        "StateDirectory=tbw-mcp\nStateDirectoryMode=0700\n"
        "Environment=TBW_MCP_STATE_DIR=/var/lib/tbw-mcp\n"
        "Restart=on-failure\nRestartSec=3\nUMask=0077\n"
        "NoNewPrivileges=yes\nPrivateTmp=yes\nProtectHome=yes\n"
        "ProtectSystem=strict\nReadOnlyPaths=/opt/tbw-mcp\n"
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

    with httpx2.Client(timeout=10, follow_redirects=False) as client:
        for attempt in range(20):
            try:
                if verify(client, "http://127.0.0.1:8879", local=True):
                    break
            except (httpx2.HTTPError, ValueError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError("La comprobación local MCP/OAuth no pasó.")

    blocks = []
    for route in sorted(routes):
        blocks.append(
            "location = " + route + " {\n"
            "    if ($scheme != https) { return 403; }\n"
            "    client_max_body_size 64k;\n"
            "    access_log off;\n"
            "    proxy_pass http://127.0.0.1:8879;\n"
            "    proxy_http_version 1.1;\n"
            "    proxy_set_header Host $host;\n"
            "    proxy_set_header Authorization $http_authorization;\n"
            "    proxy_set_header X-Forwarded-Proto $scheme;\n"
            "    proxy_buffering off;\n"
            "    proxy_request_buffering off;\n"
            "    proxy_read_timeout 90s;\n"
            "    proxy_no_cache 1;\n"
            "    proxy_cache_bypass 1;\n"
            "}\n"
        )
    with snippet.open("x") as file:
        file.write("# Managed by deploy/mcp/install.py\n" + "\n".join(blocks))
    os.chmod(snippet, 0o644)

    if site.read_bytes() != original:
        raise RuntimeError("Nginx cambió durante la instalación; no se sobrescribió.")
    changed = original_text.replace(
        anchor,
        anchor + "\n    include /etc/nginx/snippets/tbw-mcp.conf;",
        1,
    ).encode()
    site.write_bytes(changed)
    command("nginx", "-t")
    nginx_reloaded = True
    command("systemctl", "reload", "nginx")

    with httpx2.Client(timeout=15, follow_redirects=False) as client:
        for attempt in range(12):
            try:
                if verify(client, BASE_URL):
                    break
            except (httpx2.HTTPError, ValueError):
                pass
            time.sleep(2)
        else:
            raise RuntimeError("El descubrimiento OAuth o la protección HTTPS no pasó.")
        if client.get(BASE_URL + "/api/health").status_code != 200:
            raise RuntimeError("La comprobación de salud de la tienda no pasó.")

    command("systemctl", "enable", service)
    print("MCP instalado:", BASE_URL + "/mcp")
    print("Descubrimiento OAuth y metadatos de recurso: correctos por HTTPS.")
    print("MCP sin autenticación: HTTP 401.")
    print("Tienda: HTTP 200. No se reinició.")
    print("Pendiente: iniciar sesión con GitHub desde el formulario MCP.")
    print("No se crearon borradores, productos ni pedidos.")
    print("Respaldo Nginx:", backup)
except Exception as error:
    failures = []
    if service_created:
        result = subprocess.run(
            ["systemctl", "disable", "--now", service], capture_output=True
        )
        if result.returncode:
            failures.append("detener MCP")
    if changed is not None:
        if site.read_bytes() == changed:
            site.write_bytes(original)
        else:
            failures.append("Nginx tiene cambios concurrentes; revisar manualmente")
    if snippet.exists() and not failures:
        snippet.unlink()
    if nginx_reloaded and not failures:
        result = subprocess.run(["nginx", "-t"], capture_output=True)
        if result.returncode == 0:
            result = subprocess.run(
                ["systemctl", "reload", "nginx"], capture_output=True
            )
        if result.returncode:
            failures.append("recargar Nginx restaurado")
    if unit.exists():
        unit.unlink()
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
    print("Instalación incompleta:", type(error).__name__)
    if isinstance(error, RuntimeError):
        print(str(error))
    print("Credenciales y estado conservados, sin rotación.")
    print("Restauración:", ", ".join(failures) if failures else "sin errores detectados")
    raise SystemExit(1)
