"""Read-only, on-demand Search Console queries for The Books Wanderer (localhost only).

POST /query    search analytics for a date range, with optional page/query filters
POST /inspect  URL Inspection (index status) for one thebookswanderer.com URL
GET  /health

Runs as tbw-seo-agent with the same read-only service account as the weekly report
(scope webmasters.readonly). Every request needs the local admin bearer key, which only
the MCP bridge holds. Nothing is written to Google or to the website.
"""
import hmac
import json
import os
import re
import threading
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SITE = "https://thebookswanderer.com/"
SA_BASE = "https://www.googleapis.com/webmasters/v3"
INSPECT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
DIMENSIONS = {"page", "query", "date", "country", "device"}
URL_RE = re.compile(r"^https://thebookswanderer\.com/[^\s]{0,2000}$")
INSPECT_PER_HOUR = 60
PORT = 8881


def credentials_dir():
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise RuntimeError("systemd credentials are required")
    return Path(directory)


class Google:
    def __init__(self, key_file):
        creds = service_account.Credentials.from_service_account_file(str(key_file), scopes=[SCOPE])
        self.session = AuthorizedSession(creds, refresh_timeout=30)
        self.lock = threading.Lock()
        self.inspections = []

    def post(self, url, body):
        with self.lock:
            response = self.session.post(url, json=body, timeout=40)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code != 200:
            message = ""
            if isinstance(data, dict) and isinstance(data.get("error"), dict):
                message = str(data["error"].get("message", ""))[:300]
            raise GoogleError(response.status_code, message)
        return data

    def allow_inspection(self):
        now = time.time()
        with self.lock:
            self.inspections = [t for t in self.inspections if now - t < 3600]
            if len(self.inspections) >= INSPECT_PER_HOUR:
                return False
            self.inspections.append(now)
            return True


class GoogleError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class BadRequest(Exception):
    pass


def parse_date(value, name):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise BadRequest(f"{name} must be YYYY-MM-DD") from None


def build_query(body):
    today = date.today()
    end = parse_date(body.get("end_date") or (today - timedelta(days=3)).isoformat(), "end_date")
    start = parse_date(body.get("start_date") or (end - timedelta(days=27)).isoformat(), "start_date")
    if start > end or end > today or start < today - timedelta(days=490):
        raise BadRequest("dates must be within the last 16 months, start <= end <= today")
    dims = body.get("dimensions") or ["page"]
    if not isinstance(dims, list) or not dims or len(dims) > 3 or not set(dims) <= DIMENSIONS:
        raise BadRequest("dimensions: 1-3 of page, query, date, country, device")
    limit = body.get("row_limit", 50)
    if not isinstance(limit, int) or not 1 <= limit <= 250:
        raise BadRequest("row_limit must be 1-250")
    filters = []
    for key, dimension in (("page", "page"), ("query", "query")):
        value = body.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not 1 <= len(value) <= 500:
            raise BadRequest(f"{key} filter must be 1-500 characters")
        operator = "equals" if key == "page" and value.startswith("https://") else "contains"
        filters.append({"dimension": dimension, "operator": operator, "expression": value})
    country = body.get("country")
    if country is not None:
        if not isinstance(country, str) or not re.fullmatch(r"[A-Za-z]{3}", country):
            raise BadRequest("country must be a 3-letter code such as usa or chl")
        filters.append({"dimension": "country", "operator": "equals", "expression": country.lower()})
    request = {
        "startDate": start.isoformat(), "endDate": end.isoformat(), "type": "web",
        "dimensions": dims, "rowLimit": limit, "dataState": "all",
    }
    if filters:
        request["dimensionFilterGroups"] = [{"groupType": "and", "filters": filters}]
    return request


def run_query(google, body):
    request = build_query(body)
    data = google.post(SA_BASE + "/sites/" + quote(SITE, safe="") + "/searchAnalytics/query", request)
    rows = []
    for row in data.get("rows", []) if isinstance(data, dict) else []:
        item = dict(zip(request["dimensions"], row.get("keys", [])))
        item.update({"clicks": row.get("clicks", 0), "impressions": row.get("impressions", 0),
                     "ctr": round(row.get("ctr", 0), 4), "position": round(row.get("position", 0), 2)})
        rows.append(item)
    return {"site": SITE, "start_date": request["startDate"], "end_date": request["endDate"],
            "dimensions": request["dimensions"], "filters": request.get("dimensionFilterGroups", []),
            "rows": rows, "row_count": len(rows), "row_limit_reached": len(rows) >= request["rowLimit"],
            "note": "Includes fresh (non-final) data. Google omits anonymized queries and rare rows."}


def run_inspect(google, body):
    url = body.get("url")
    if not isinstance(url, str) or not URL_RE.fullmatch(url):
        raise BadRequest("url must be a full https://thebookswanderer.com/ address")
    if not google.allow_inspection():
        raise BadRequest(f"inspection limit reached ({INSPECT_PER_HOUR} per hour); try later")
    data = google.post(INSPECT, {"inspectionUrl": url, "siteUrl": SITE, "languageCode": "en-US"})
    result = (data or {}).get("inspectionResult", {}) or {}
    index = result.get("indexStatusResult", {}) or {}
    mobile = result.get("mobileUsabilityResult", {}) or {}
    rich = result.get("richResultsResult", {}) or {}
    return {
        "url": url,
        "verdict": index.get("verdict"),
        "coverage_state": index.get("coverageState"),
        "indexing_state": index.get("indexingState"),
        "page_fetch_state": index.get("pageFetchState"),
        "robots_txt_state": index.get("robotsTxtState"),
        "last_crawl_time": index.get("lastCrawlTime"),
        "crawled_as": index.get("crawledAs"),
        "google_canonical": index.get("googleCanonical"),
        "user_canonical": index.get("userCanonical"),
        "in_sitemaps": (index.get("sitemap") or [])[:5],
        "referring_urls": (index.get("referringUrls") or [])[:10],
        "mobile_usability": mobile.get("verdict"),
        "rich_results": rich.get("verdict"),
        "rich_result_types": [d.get("richResultType") for d in rich.get("detectedItems", []) or []][:10],
        "inspection_link": result.get("inspectionResultLink"),
        "note": "Read-only. Requesting indexing is only possible by hand in Search Console.",
    }


class Handler(BaseHTTPRequestHandler):
    google = None
    key = ""

    def log_message(self, *args):
        pass

    def reply(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        header = self.headers.get("Authorization", "")
        return header.startswith("Bearer ") and hmac.compare_digest(header[7:].strip(), self.key)

    def do_GET(self):
        if self.path == "/health" and self.authorized():
            return self.reply(200, {"ok": True})
        self.reply(404, {"detail": "not found"})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {"detail": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise BadRequest("body must be 1-8192 bytes of JSON")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise BadRequest("body must be a JSON object")
            if self.path == "/query":
                return self.reply(200, run_query(self.google, body))
            if self.path == "/inspect":
                return self.reply(200, run_inspect(self.google, body))
            return self.reply(404, {"detail": "not found"})
        except (BadRequest, json.JSONDecodeError, ValueError) as error:
            return self.reply(400, {"detail": str(error)[:300]})
        except GoogleError as error:
            return self.reply(502, {"detail": f"Search Console HTTP {error.status}: {error.message}"})
        except Exception as error:  # noqa: BLE001
            return self.reply(502, {"detail": "Search Console request failed: " + type(error).__name__})


def main():
    directory = credentials_dir()
    Handler.key = (directory / "admin_key").read_text().strip()
    if len(Handler.key) < 32:
        raise RuntimeError("admin key unavailable")
    Handler.google = Google(directory / "google-service-account.json")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
