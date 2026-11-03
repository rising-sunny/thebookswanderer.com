#!/usr/bin/env python3
"""One-time root install: the local read-only Search Console query service and two MCP tools.

1. /opt/tbw-seo-query/seo_query.py + tbw-seo-query.service (user tbw-seo-agent, the weekly
   report's read-only service account, localhost:8881, admin bearer key). Checked with /health.
2. Inserts tbw_seo_query and tbw_seo_inspect_url into the installed /opt/tbw-mcp/tbw_mcp.py,
   right before tbw_health, with a timestamped backup; compiles, restarts tbw-mcp and restores
   the backup if the service does not come back. Idempotent.
"""
import json
import py_compile
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPT = Path("/opt/tbw-seo-query")
UNIT = Path("/etc/systemd/system/tbw-seo-query.service")
MCP = Path("/opt/tbw-mcp/tbw_mcp.py")
ANCHOR = "    @server.tool(annotations=READ)\n    async def tbw_health() -> dict:\n"
MARK = "# --- Search Console on demand"
KEY = Path("/etc/tbw-admin-api/key")

UNIT_TEXT = """[Unit]
Description=The Books Wanderer read-only Search Console queries (localhost)
After=network-online.target
Wants=network-online.target

[Service]
User=tbw-seo-agent
Group=tbw-seo-agent
ExecStart=/opt/tbw-seo-agent/.venv/bin/python /opt/tbw-seo-query/seo_query.py
LoadCredential=google-service-account.json:/etc/tbw-seo-agent/google-service-account.json
LoadCredential=admin_key:/etc/tbw-admin-api/key
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
"""


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def health():
    req = urllib.request.Request("http://127.0.0.1:8881/health",
                                 headers={"Authorization": "Bearer " + KEY.read_text().strip()})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def install_service():
    OPT.mkdir(mode=0o755, exist_ok=True)
    shutil.copy2(HERE / "seo_query.py", OPT / "seo_query.py")
    (OPT / "seo_query.py").chmod(0o644)
    UNIT.write_text(UNIT_TEXT)
    sh("systemctl", "daemon-reload")
    sh("systemctl", "enable", "tbw-seo-query.service")
    sh("systemctl", "restart", "tbw-seo-query.service")
    for _ in range(15):
        time.sleep(1)
        if health():
            print("tbw-seo-query: active, health ok")
            return True
    print("tbw-seo-query: NOT healthy;", sh("systemctl", "is-active", "tbw-seo-query").stdout.strip())
    print(sh("journalctl", "-u", "tbw-seo-query", "-n", "15", "--no-pager", "-o", "cat").stdout[-1500:])
    return False


def patch_mcp():
    src = MCP.read_text()
    if MARK in src:
        print("tbw-mcp: tools already present")
        return True
    if src.count(ANCHOR) != 1:
        print("tbw-mcp: anchor not found exactly once; not patched")
        return False
    backup = MCP.with_name(f"tbw_mcp.before-seo-query-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.py")
    shutil.copy2(MCP, backup)
    MCP.write_text(src.replace(ANCHOR, (HERE / "mcp_tools.py").read_text() + ANCHOR))
    try:
        py_compile.compile(str(MCP), doraise=True, cfile="/tmp/tbw_mcp_check.pyc")
    except py_compile.PyCompileError as error:
        shutil.copy2(backup, MCP)
        print("tbw-mcp: patched file did not compile, restored:", str(error)[:300])
        return False
    sh("systemctl", "restart", "tbw-mcp.service")
    time.sleep(6)
    if sh("systemctl", "is-active", "tbw-mcp.service").stdout.strip() != "active":
        print("tbw-mcp: did not come back after patch; restoring backup")
        print(sh("journalctl", "-u", "tbw-mcp", "-n", "20", "--no-pager", "-o", "cat").stdout[-2000:])
        shutil.copy2(backup, MCP)
        sh("systemctl", "restart", "tbw-mcp.service")
        time.sleep(4)
        print("tbw-mcp after restore:", sh("systemctl", "is-active", "tbw-mcp.service").stdout.strip())
        return False
    print("tbw-mcp: tools added and service active; backup", backup.name)
    return True


if __name__ == "__main__":
    ok = install_service() and patch_mcp()
    sys.exit(0 if ok else 1)
