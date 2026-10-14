#!/usr/bin/env python3
"""Read-only production diagnostics; never send mail, orders, or Meta events.

Run from server: .venv/bin/python scripts/check_integrations.py
Credentials stay in server/.env. Output contains only predefined status fields.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def result(status: str, detail: str, **fields) -> dict:
    return {"status": status, "detail": detail, **fields}


def missing(*names: str) -> list[str]:
    return [name for name in names if not os.getenv(name, "").strip()]


def paypal(client) -> dict:
    absent = missing("PAYPAL_CLIENT_ID", "PAYPAL_SECRET")
    if absent:
        return result("FAIL", "Missing configuration", missing=absent)
    mode = os.getenv("PAYPAL_MODE", "live")
    if mode not in {"live", "sandbox"}:
        return result("FAIL", "PAYPAL_MODE must be live or sandbox")
    host = "api-m.paypal.com" if mode == "live" else "api-m.sandbox.paypal.com"
    response = client.post(
        f"https://{host}/v1/oauth2/token",
        auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_SECRET"]),
        data={"grant_type": "client_credentials"},
    )
    if response.status_code != 200:
        return result("FAIL", "OAuth token request rejected", http_status=response.status_code, mode=mode)
    if not response.json().get("access_token"):
        return result("FAIL", "OAuth response did not contain an access token")
    return result("PASS", "OAuth authentication succeeded; no orders created", mode=mode)


def smtp() -> dict:
    absent = missing("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM")
    if absent:
        return result("FAIL", "Missing configuration", missing=absent)
    use_ssl = os.getenv("SMTP_SSL", "").lower() in {"1", "true", "yes"}
    starttls = os.getenv("SMTP_STARTTLS", "1").lower() not in {"0", "false", "no"}
    if not use_ssl and not starttls:
        return result("FAIL", "Refusing password authentication without TLS")
    context = ssl.create_default_context()
    port = int(os.getenv("SMTP_PORT", "587"))
    kwargs = {"host": os.environ["SMTP_HOST"], "port": port, "timeout": 20}
    connection = smtplib.SMTP_SSL(**kwargs, context=context) if use_ssl else smtplib.SMTP(**kwargs)
    with connection as server:
        server.ehlo()
        if not use_ssl:
            server.starttls(context=context)
            server.ehlo()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
    return result("PASS", "TLS and SMTP authentication succeeded; no email sent")


def meta(client) -> dict:
    absent = missing("META_PIXEL_ID", "META_CAPI_TOKEN")
    if absent:
        return result("FAIL", "Missing configuration", missing=absent)
    token = os.environ["META_CAPI_TOKEN"]
    base = "https://graph.facebook.com/v21.0"
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get(f"{base}/debug_token", headers=headers, params={"input_token": token})
    if response.status_code != 200:
        return result("LIMITED", "Token introspection unavailable; CAPI delivery remains unverified", http_status=response.status_code)
    data = response.json().get("data") or {}
    if data.get("is_valid") is not True:
        return result("FAIL", "Meta reports an invalid token")
    scopes = data.get("scopes") or []
    response = client.get(f"{base}/{os.environ['META_PIXEL_ID']}", headers=headers, params={"fields": "id"})
    if response.status_code != 200:
        return result("LIMITED", "Token valid, but dataset read access unverified; this does not prove CAPI rejection", http_status=response.status_code)
    if str(response.json().get("id")) != os.environ["META_PIXEL_ID"]:
        return result("FAIL", "Dataset response identity mismatch")
    return result("PASS", "Token valid and dataset readable; event delivery NOT tested", ads_management="ads_management" in scopes, expires_at=data.get("expires_at"))


def uptimerobot(client) -> dict:
    absent = missing("UPTIMEROBOT_API_KEY")
    if absent:
        return result("FAIL", "Missing configuration", missing=absent)
    response = client.post("https://api.uptimerobot.com/v2/getMonitors", data={
        "api_key": os.environ["UPTIMEROBOT_API_KEY"], "format": "json", "logs": "0",
    })
    if response.status_code != 200:
        return result("FAIL", "Monitor query rejected", http_status=response.status_code)
    data = response.json()
    if data.get("stat") != "ok":
        return result("FAIL", "UptimeRobot rejected the API request")
    from urllib.parse import urlparse
    monitors = [m for m in data.get("monitors", []) if urlparse(m.get("url", "")).hostname in {"thebookswanderer.com", "www.thebookswanderer.com"}]
    if not monitors:
        return result("LIMITED", "Authentication succeeded; no matching website monitor returned")
    states = [m.get("status") for m in monitors]
    return result("PASS" if all(s == 2 for s in states) else "FAIL", "Authentication succeeded; 2=up, 0=paused, 1=pending, 8=seems down, 9=down", monitor_states=states)


def safe_check(fn) -> dict:
    try:
        return fn()
    except Exception as exc:
        # Exception messages, URLs and response bodies can contain credentials.
        fields = {"error_type": type(exc).__name__}
        if isinstance(exc, smtplib.SMTPResponseException):
            fields["smtp_code"] = exc.smtp_code
        return result("FAIL", "Check failed; exception content withheld", **fields)


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        checks = {
            "paypal": safe_check(lambda: paypal(client)),
            "smtp": safe_check(smtp),
            "meta_capi": safe_check(lambda: meta(client)),
            "uptimerobot": safe_check(lambda: uptimerobot(client)),
        }
    print(json.dumps({"checks": checks}, indent=2), flush=True)
    return int(any(check["status"] == "FAIL" for check in checks.values()))


if __name__ == "__main__":
    sys.exit(main())
