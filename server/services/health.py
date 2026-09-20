"""
Chequeos de salud del servidor para el panel /admin/live.

Un panel que vive en el servidor NO puede avisar de que el servidor esta caido:
cuando nginx murio tres dias en septiembre de 2026, /admin/live estaba igual de
muerto. Por eso hay dos mitades:

  - Chequeos internos (esta funcion): nginx, disco, RAM, certificado, unidades
    fallidas, cron... Utiles cuando el panel carga.
  - UptimeRobot, desde fuera: pide /api/health cada 5 min y manda email si
    falla. ESA es la alerta real. Este panel solo consulta su API de solo
    lectura para mostrar lo que UptimeRobot ve (estado, % de uptime).

Todo corre como www-data: nada aqui necesita root. Los chequeos lentos
(systemctl, TLS) se cachean 60 s para que el panel no los repita a cada refresco.
"""
from __future__ import annotations

import os
import shutil
import socket
import ssl
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CART_LOG = Path("/var/log/tbw-cart-reminders.log")

_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: int, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def _run(*cmd: str, timeout: int = 5) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


# ── Chequeos individuales ─────────────────────────────────────────────────
# Cada uno devuelve {"ok": bool, "value": str, "detail": str}.


def check_nginx() -> dict:
    st = _cached("nginx", 60, lambda: _run("systemctl", "is-active", "nginx"))
    return {"ok": st == "active", "value": st or "unknown",
            "detail": "front door; if this is down the shop is unreachable"}


def check_failed_units() -> dict:
    out = _cached("failed", 60, lambda: _run("systemctl", "--failed", "--no-legend", "--plain"))
    names = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
    return {"ok": not names, "value": str(len(names)),
            "detail": ", ".join(names) if names else "no failed systemd units"}


def check_reboot() -> dict:
    pending = Path("/var/run/reboot-required").exists()
    return {"ok": not pending, "value": "pending" if pending else "no",
            "detail": "kernel or libc updated; reboot in a quiet hour" if pending else ""}


def check_disk() -> dict:
    u = shutil.disk_usage("/")
    pct = round(u.used * 100 / u.total)
    free_gb = round(u.free / 1e9, 1)
    return {"ok": pct < 85, "value": f"{pct}% used", "detail": f"{free_gb} GB free"}


def check_memory() -> dict:
    try:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            info[k] = int(v.strip().split()[0])  # kB
        total, avail = info["MemTotal"], info["MemAvailable"]
        pct = round((total - avail) * 100 / total)
        return {"ok": pct < 90, "value": f"{pct}% used",
                "detail": f"{round(avail / 1024)} MB available"}
    except Exception:  # noqa: BLE001
        return {"ok": True, "value": "n/a", "detail": ""}


def check_cert(host: str = "thebookswanderer.com") -> dict:
    """Lee el certificado conectando a 127.0.0.1:443 con SNI.

    /etc/letsencrypt/live es solo root; www-data no puede leerlo. Pero puede
    hacer un handshake TLS contra el propio nginx y leer la fecha de ahi.
    """
    def fetch():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection(("127.0.0.1", 443), timeout=4) as s:
            with ctx.wrap_socket(s, server_hostname=host) as tls:
                der = tls.getpeercert(binary_form=True)
        # Sin cryptography instalado: extraer notAfter via openssl CLI.
        out = subprocess.run(
            ["openssl", "x509", "-inform", "DER", "-noout", "-enddate"],
            input=der, capture_output=True, timeout=5,
        ).stdout.decode()
        raw = out.strip().split("=", 1)[1]
        exp = datetime.strptime(raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        return exp

    try:
        exp = _cached("cert", 3600, fetch)
        days = (exp - datetime.now(timezone.utc)).days
        return {"ok": days > 14, "value": f"{days} days",
                "detail": f"expires {exp:%Y-%m-%d}; certbot renews at 30"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "value": "unreadable", "detail": str(e)[:80]}


def check_cart_cron() -> dict:
    """El cron de recordatorios escribe en su log cada hora, incluso sin envios."""
    try:
        age = time.time() - CART_LOG.stat().st_mtime
        hours = age / 3600
        return {"ok": hours < 2.5, "value": f"{hours:.1f} h ago",
                "detail": "hourly cron; >2.5 h means it stopped running"}
    except FileNotFoundError:
        return {"ok": False, "value": "no log", "detail": f"{CART_LOG} missing"}
    except PermissionError:
        return {"ok": True, "value": "n/a", "detail": "log not readable by www-data"}


def check_uptimerobot() -> dict:
    """Lo que UptimeRobot ve desde fuera. API v2, clave de SOLO LECTURA.

    Cacheado 60 s: el plan gratuito permite 10 llamadas/min y el panel
    refresca cada 30 s desde cada pestana abierta.
    """
    key = (os.getenv("UPTIMEROBOT_API_KEY") or "").strip()
    if not key:
        return {"ok": True, "value": "not configured",
                "detail": "add the read-only API key as UPTIMEROBOT_API_KEY in .env"}

    def fetch():
        import httpx
        r = httpx.post(
            "https://api.uptimerobot.com/v2/getMonitors",
            data={"api_key": key, "format": "json",
                  "custom_uptime_ratios": "1-7-30", "logs": "1", "logs_limit": "1"},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()

    try:
        data = _cached("uptimerobot", 60, fetch)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "value": "api error", "detail": str(e)[:80]}

    if data.get("stat") != "ok":
        msg = (data.get("error") or {}).get("message", "unknown error")
        return {"ok": False, "value": "api error", "detail": msg[:80]}

    mons = data.get("monitors") or []
    mon = next((m for m in mons if "thebookswanderer" in (m.get("url") or "")), None)         or (mons[0] if mons else None)
    if not mon:
        return {"ok": False, "value": "no monitor",
                "detail": "the API key works but no monitor is defined yet"}

    status = int(mon.get("status", 0))
    labels = {0: "paused", 1: "not checked yet", 2: "UP", 8: "seems down", 9: "DOWN"}
    ratios = (mon.get("custom_uptime_ratio") or "").split("-")
    r7 = ratios[1] if len(ratios) > 1 else "?"
    r30 = ratios[2] if len(ratios) > 2 else "?"
    detail = f"uptime {r7}% (7d) / {r30}% (30d) — checked every {int(mon.get('interval', 0)) // 60} min"
    return {"ok": status == 2, "value": labels.get(status, str(status)), "detail": detail}


def snapshot() -> dict:
    """Todo junto, en el orden en que conviene leerlo."""
    checks = {
        "external_probe": check_uptimerobot(),
        "nginx": check_nginx(),
        "tls_certificate": check_cert(),
        "failed_units": check_failed_units(),
        "reboot_required": check_reboot(),
        "disk": check_disk(),
        "memory": check_memory(),
        "cart_reminder_cron": check_cart_cron(),
    }
    return {
        "all_ok": all(c["ok"] for c in checks.values()),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
    }
