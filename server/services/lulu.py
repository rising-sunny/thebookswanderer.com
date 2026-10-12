"""
Lulu Print API client (print-on-demand books and booklets).

Paid orders become Lulu print jobs; Lulu fetches the interior and cover
PDFs from /api/print-files/<name>?sig=…, a signed link to the private
DIGITAL_DIR, and charges the card on file in the Lulu account.

Env:
  LULU_CLIENT_KEY / LULU_CLIENT_SECRET   API keys (developers.lulu.com > API Keys)
  LULU_ENV                               "production" (default) or "sandbox"
  LULU_SHIP_COUNTRIES                    where printed books are offered (shipping
                                         is included in the price, so only
                                         countries with a sane MAIL rate)
  LULU_SHIPPING_LEVEL                    MAIL (default), PRIORITY_MAIL, GROUND…
  LULU_CONTACT_EMAIL                     who Lulu writes to about a job
Docs: https://api.lulu.com/docs/
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from typing import Any

import httpx

_TOKEN: dict[str, Any] = {}

SUPPLIER = "lulu"
# Quoted 2026-10: A5 colour paperback, 40 pages, MAIL: US 5.69, GB 5.22,
# AU 8.34, DE 7.04, NL 7.76, FR 9.83, IE 10.16, CA 10.92 (+ ~4 print).
# ES and IT need a province code and MX/CL a tax id, so they wait.
DEFAULT_COUNTRIES = "US,GB,CA,AU,DE,FR,NL,IE"
ETA_DAYS = "10-20"  # 3-5 business days printing + MAIL transit

CA_PROVINCES = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB",
    "newfoundland and labrador": "NL", "nova scotia": "NS", "ontario": "ON",
    "prince edward island": "PE", "quebec": "QC", "québec": "QC", "saskatchewan": "SK",
    "northwest territories": "NT", "nunavut": "NU", "yukon": "YT",
}
AU_STATES = {
    "new south wales": "NSW", "victoria": "VIC", "queensland": "QLD", "western australia": "WA",
    "south australia": "SA", "tasmania": "TAS", "australian capital territory": "ACT",
    "northern territory": "NT",
}


class LuluError(RuntimeError):
    def __init__(self, message: str, payload: Any = None):
        super().__init__(message)
        self.payload = payload


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def base() -> str:
    return "https://api.sandbox.lulu.com" if _env("LULU_ENV") == "sandbox" else "https://api.lulu.com"


def ship_countries() -> set[str]:
    raw = _env("LULU_SHIP_COUNTRIES") or DEFAULT_COUNTRIES
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def ships_to(country_code: str) -> bool:
    return (country_code or "").upper() in ship_countries()


def file_sig(name: str) -> str:
    secret = _env("SECRET_KEY")
    return hmac.new(secret.encode(), f"print:{name}".encode(), hashlib.sha256).hexdigest()[:32]


def check_file_sig(name: str, sig: str | None) -> bool:
    return bool(sig) and bool(_env("SECRET_KEY")) and hmac.compare_digest(file_sig(name), sig or "")


def file_url(base_url: str, name: str) -> str:
    return f"{base_url.rstrip('/')}/api/print-files/{name}?sig={file_sig(name)}"


def state_code(country: str, province: str) -> str:
    from services.printify import region_code

    p = (province or "").strip()
    country = (country or "").upper()
    if country == "US":
        return region_code(p)
    table = {"CA": CA_PROVINCES, "AU": AU_STATES}.get(country, {})
    return table.get(p.lower(), p.upper() if len(p) <= 3 else p)


def _split_street(line1: str, line2: str, limit: int = 30) -> tuple[str, str]:
    """Lulu caps street lines at 30 characters: wrap the overflow of the
    first line into the second at a word break."""
    line1, line2 = (line1 or "").strip(), (line2 or "").strip()
    if len(line1) <= limit:
        return line1, line2
    cut = line1.rfind(" ", 0, limit + 1)
    cut = cut if cut > 0 else limit
    head, rest = line1[:cut].strip(), line1[cut:].strip()
    return head, " ".join(x for x in (rest, line2) if x)


def address(name: str, line1: str, line2: str, city: str, province: str, country: str,
            postcode: str, phone: str) -> dict[str, str]:
    street1, street2 = _split_street(line1, line2)
    if len(street2) > 30:
        raise LuluError(f"address too long for Lulu's 30-character street lines: {line1!r} / {line2!r}")
    out = {
        "name": (name or "").strip()[:60] or "Customer",
        "street1": street1,
        "city": (city or "").strip(),
        "country_code": (country or "").upper(),
        "postcode": (postcode or "").strip(),
        "phone_number": re.sub(r"[^0-9+]", "", phone or "") or "0000000000",
    }
    if street2:
        out["street2"] = street2
    st = state_code(country, province)
    if st:
        out["state_code"] = st
    return out


def configured() -> bool:
    return bool(_env("LULU_CLIENT_KEY") and _env("LULU_CLIENT_SECRET"))


async def _token(client: httpx.AsyncClient) -> str:
    if _TOKEN.get("value") and _TOKEN.get("expires", 0) > time.time() + 60:
        return _TOKEN["value"]
    r = await client.post(
        f"{base()}/auth/realms/glasstree/protocol/openid-connect/token",
        auth=(_env("LULU_CLIENT_KEY"), _env("LULU_CLIENT_SECRET")),
        data={"grant_type": "client_credentials"},
    )
    if r.status_code != 200:
        raise LuluError(f"auth failed: HTTP {r.status_code}", r.text[:300])
    data = r.json()
    _TOKEN.update(value=data["access_token"], expires=time.time() + int(data.get("expires_in", 300)))
    return _TOKEN["value"]


async def request(method: str, path: str, json: Any = None) -> Any:
    if not configured():
        raise LuluError("LULU_CLIENT_KEY / LULU_CLIENT_SECRET not set")
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _token(client)
        r = await client.request(
            method, f"{base()}{path}", json=json, headers={"Authorization": f"Bearer {token}"}
        )
    if r.status_code >= 400:
        try:
            payload = r.json()
        except ValueError:
            payload = r.text[:500]
        raise LuluError(f"{method} {path}: HTTP {r.status_code}", payload)
    return r.json() if r.content else None


async def cost(pod_package_id: str, page_count: int, quantity: int, address: dict[str, str],
               shipping_option: str = "MAIL") -> dict[str, Any]:
    """Print + shipping cost for one line item (no order is created)."""
    return await request("POST", "/print-job-cost-calculations/", {
        "line_items": [{"pod_package_id": pod_package_id, "page_count": page_count, "quantity": quantity}],
        "shipping_address": address,
        "shipping_option": shipping_option,
    })


async def create_print_job(external_id: str, lines: list[dict[str, Any]], shipping_address: dict[str, str]) -> dict:
    """lines: [{"title", "pod_package_id", "interior_url", "cover_url", "quantity", "external_id"}]"""
    return await request("POST", "/print-jobs/", {
        "external_id": external_id,
        "contact_email": _env("LULU_CONTACT_EMAIL") or "hello@thebookswanderer.com",
        "shipping_level": _env("LULU_SHIPPING_LEVEL") or "MAIL",
        "shipping_address": shipping_address,
        "line_items": [
            {
                "external_id": ln["external_id"],
                "title": ln["title"][:250],
                "quantity": ln["quantity"],
                "printable_normalization": {
                    "pod_package_id": ln["pod_package_id"],
                    "interior": {"source_url": ln["interior_url"]},
                    "cover": {"source_url": ln["cover_url"]},
                },
            }
            for ln in lines
        ],
    })
