import ipaddress
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


# Meta's own networks (AS32934). Fallback for when ip-api is unreachable; the
# ASN it returns is the primary signal.
_META_NETS = [ipaddress.ip_network(n) for n in (
    "31.13.24.0/21", "31.13.64.0/18", "45.64.40.0/22", "57.141.0.0/16",
    "57.144.0.0/14", "66.220.144.0/20", "69.63.176.0/20", "69.171.224.0/19",
    "74.119.76.0/22", "102.132.96.0/20", "103.4.96.0/22", "129.134.0.0/16",
    "147.75.208.0/20", "157.240.0.0/16", "163.70.128.0/17", "173.252.64.0/18",
    "179.60.192.0/22", "185.60.216.0/22", "185.89.216.0/22", "204.15.20.0/22",
    "2a03:2880::/32", "2620:0:1c00::/40",
)]
_NO_GEO = {"country": None, "country_name": None, "city": None, "asn": None, "hosting": False}


def is_meta_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _META_NETS)


def _is_private(ip: str) -> bool:
    return ip.startswith(_PRIVATE_PREFIXES) or ip in ("::1", "")


def lookup(ip: str) -> dict:
    if not ip or _is_private(ip):
        return dict(_NO_GEO)

    now = time.time()
    with _LOCK:
        hit = _CACHE.get(ip)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

    try:
        r = httpx.get(
            f"http://ip-api.com/json/{ip}?fields=status,countryCode,country,city,as,hosting",
            timeout=2.0,
        )
        data = r.json() if r.status_code == 200 else {}
    except Exception:
        data = {}

    result = {
        "country": data.get("countryCode"),
        "country_name": data.get("country"),
        "city": data.get("city"),
        "asn": data.get("as") or None,
        "hosting": bool(data.get("hosting")),
    } if data.get("status") == "success" else dict(_NO_GEO)

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
