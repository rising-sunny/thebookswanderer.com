import threading
import time
from typing import Optional, Tuple

import httpx

_CACHE: dict[str, Tuple[float, dict]] = {}
_CACHE_TTL = 24 * 3600
_LOCK = threading.Lock()

_PRIVATE_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                     "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                     "172.30.", "172.31.", "192.168.", "127.", "0.")


def _is_private(ip: str) -> bool:
    return ip.startswith(_PRIVATE_PREFIXES) or ip in ("::1", "")


def lookup(ip: str) -> dict:
    if not ip or _is_private(ip):
        return {"country": None, "country_name": None, "city": None}

    now = time.time()
    with _LOCK:
        hit = _CACHE.get(ip)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

    try:
        r = httpx.get(
            f"http://ip-api.com/json/{ip}?fields=status,countryCode,country,city",
            timeout=2.0,
        )
        data = r.json() if r.status_code == 200 else {}
    except Exception:
        data = {}

    result = {
        "country": data.get("countryCode"),
        "country_name": data.get("country"),
        "city": data.get("city"),
    } if data.get("status") == "success" else {"country": None, "country_name": None, "city": None}

    with _LOCK:
        _CACHE[ip] = (now, result)
        if len(_CACHE) > 5000:
            cutoff = now - _CACHE_TTL
            for k in [k for k, v in _CACHE.items() if v[0] < cutoff]:
                _CACHE.pop(k, None)
    return result


def extract_client_ip(request) -> Optional[str]:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
