"""Restricted administrative API: store reads, read-only CJ search, drafts."""
import hmac
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone as utc_timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

bearer = HTTPBearer(auto_error=False)

def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    directory = os.getenv("CREDENTIALS_DIRECTORY", "")
    path = (
        Path(directory) / "admin_key" if directory
        else Path(os.getenv("TBW_ADMIN_KEY_FILE", "/etc/tbw-admin-api/key"))
    )
    try:
        expected = path.read_text().strip()
    except OSError:
        raise HTTPException(503, "Administrative credential unavailable")
    if len(expected) < 32:
        raise HTTPException(503, "Administrative credential unavailable")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not hmac.compare_digest(
            credentials.credentials.encode(), expected.encode()
        )
    ):
        raise HTTPException(
            401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"}
        )

app = FastAPI(
    docs_url=None, redoc_url=None, openapi_url=None,
    dependencies=[Depends(authorize)],
)

@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

STORE_API = "http://127.0.0.1:8010"
store_transport = None  # tests replace it
CJ_ID = r"^[A-Za-z0-9-]{1,64}$"

def credential(name, variable):
    directory = os.getenv("CREDENTIALS_DIRECTORY", "")
    path = Path(directory) / name if directory else Path(os.getenv(variable, ""))
    try:
        value = path.read_text().strip() if str(path) not in {"", "."} else ""
    except OSError:
        value = ""
    if not value:
        raise HTTPException(503, "Supplier credential unavailable")
    return value

def cj_module():
    """The storefront's CJ client, fed only the CJ credential."""
    os.environ["CJ_API_KEY"] = credential("cj_api_key", "TBW_CJ_KEY_FILE")
    server = os.getenv("TBW_STORE_SERVER", "/var/www/thebookswanderer.com/server")
    if server not in sys.path:
        sys.path.insert(0, server)
    from services import cj
    return cj

def store():
    path = Path(os.getenv(
        "TBW_ADMIN_STORE_DB",
        "/var/www/thebookswanderer.com/server/data/store.db",
    ))
    uri = path.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db

def owned_cj_pids(pids):
    if not pids:
        return set()
    marks = ",".join("?" * len(pids))
    with closing(store()) as db:
        rows = db.execute(
            f"SELECT cj_pid FROM products WHERE cj_pid IN ({marks})", list(pids)
        ).fetchall()
    return {row["cj_pid"] for row in rows}

async def retail_prices(costs):
    """Suggested retail per cost, from the storefront's own pricing rules."""
    prices = {}
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for cost in sorted(set(costs)):
            try:
                response = await client.get(
                    STORE_API + "/api/pricing/preview", params={"cost_usd": cost}
                )
                prices[cost] = float(response.json()["price_usd"])
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                prices[cost] = None
    return prices

def number(value):
    """CJ sends either a scalar or a "1.20-3.40" range; keep the low end."""
    if isinstance(value, str) and "-" in value:
        value = value.split("-")[0]
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0

async def cj_call(name, *args, **kwargs):
    cj = cj_module()
    try:
        return await getattr(cj, name)(*args, **kwargs)
    except cj.CJError:
        raise HTTPException(502, "CJ request failed") from None
    except httpx.HTTPError:
        raise HTTPException(502, "CJ unavailable") from None

@app.exception_handler(sqlite3.Error)
async def database_error(request, error):
    return JSONResponse(
        status_code=503, content={"detail": "Administrative storage unavailable"}
    )

@app.get("/health")
def health():
    return {
        "service": "tbw-admin-api",
        "ready": True,
        "capabilities": [
            "products:read", "cj:read", "products:draft", "products:publish",
            "printify:read", "prodigi:read", "shipping:quote", "suppliers:api", "crosslist",
            "products:activity", "etsy:listings:read",
        ],
        "order_submission_enabled": False,
        # Drafts only, each with the code from its publication preview.
        "product_publication_enabled": True,
    }

@app.get("/products")
def products(limit: int = Query(default=50, ge=1, le=100),
             offset: int = Query(default=0, ge=0)):
    with closing(store()) as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(products)")}
        extra = ", ".join(name if name in columns else f"NULL AS {name}" for name in (
            "created_at", "etsy_listing_id", "printify_product_id", "printify_twin_id",
        ))
        rows = db.execute(f"""
            SELECT id, slug, title, supplier, price_usd, active, draft, {extra}
            FROM products ORDER BY id LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        ledger = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_publication_events'").fetchone()
        latest = {}
        if ledger and rows:
            marks = ",".join("?" for row in rows)
            latest = {(row["product_id"], row["product_slug"]): row["published_at"] for row in db.execute(
                f"""SELECT product_id, product_slug, MAX(occurred_at) AS published_at
                    FROM product_publication_events WHERE event_type='published'
                    AND product_id IN ({marks}) GROUP BY product_id, product_slug""",
                [row["id"] for row in rows],
            )}
    items = [dict(row) for row in rows]
    for item in items:
        item["created_at"] = iso_timestamp(item["created_at"])
        item["published_at"] = None  # Never substitute the creation date.
        item["last_recorded_publication_at"] = iso_timestamp(latest.get((item["id"], item["slug"])))
    return {"products": items, "limit": limit, "offset": offset,
            "date_note": "created_at is row creation, not publication; use product activity for publication receipts."}


def iso_timestamp(value):
    """Store DateTime columns are UTC, including SQLite's naive encoding."""
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=utc_timezone.utc)
    return stamp.astimezone(utc_timezone.utc).isoformat().replace("+00:00", "Z")


def activity_window(day, timezone):
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Unknown IANA timezone") from None
    try:
        start = datetime.combine(day, time.min, zone)
        end = datetime.combine(day + timedelta(days=1), time.min, zone)
    except OverflowError:
        raise HTTPException(422, "Day is outside the supported date range") from None
    return start.astimezone(utc_timezone.utc), end.astimezone(utc_timezone.utc)


@app.get("/products/activity")
def product_activity(day: date,
                     timezone: str = Query(default="America/Santiago", max_length=80),
                     platform: Literal["all", "store", "pinterest"] = "all",
                     product_id: int | None = Query(default=None, ge=1),
                     limit: int = Query(default=50, ge=1, le=100),
                     offset: int = Query(default=0, ge=0)):
    start, end = activity_window(day, timezone)
    with closing(store()) as db:
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        pcols = {row["name"] for row in db.execute("PRAGMA table_info(products)")}
        sources = []
        if platform in {"all", "store"} and "created_at" in pcols:
            sources.append("""SELECT 'created:' || id AS event_id, id AS product_id,
                slug, title, 'store' AS platform, 'product_created' AS event_type,
                created_at AS occurred_at, 'products.created_at' AS source,
                NULL AS external_id FROM products""")
        if platform in {"all", "store"} and "product_publication_events" in tables:
            sources.append("""SELECT 'publication:' || id AS event_id, product_id,
                product_slug AS slug, product_title AS title, platform, event_type,
                occurred_at, source, NULL AS external_id FROM product_publication_events
                WHERE event_type IN ('published', 'unpublished')""")
        if platform in {"all", "pinterest"} and "pinterest_pins" in tables:
            sources.append("""SELECT 'pin:' || pin.id AS event_id, pin.product_id,
                pin.product_slug AS slug, p.title, 'pinterest' AS platform,
                'pin_recorded' AS event_type, pin.created_at AS occurred_at,
                'pinterest_pins.created_at' AS source, pin.pin_id AS external_id
                FROM pinterest_pins pin LEFT JOIN products p ON p.id = pin.product_id
                WHERE pin.status = 'active' AND pin.pin_id != ''""")
        started = None
        if "product_publication_events" in tables:
            row = db.execute("""SELECT MIN(occurred_at) AS started FROM product_publication_events
                WHERE event_type = 'tracking_started'""").fetchone()
            started = iso_timestamp(row["started"])
        events, total = [], 0
        if sources:
            query = " FROM (" + " UNION ALL ".join(sources) + ") WHERE julianday(occurred_at) >= julianday(?) AND julianday(occurred_at) < julianday(?)"
            params = [start.isoformat(), end.isoformat()]
            if product_id is not None:
                query += " AND product_id = ?"
                params.append(product_id)
            total = db.execute("SELECT COUNT(*)" + query, params).fetchone()[0]
            rows = db.execute("SELECT *" + query + " ORDER BY julianday(occurred_at), event_id LIMIT ? OFFSET ?",
                              [*params, limit, offset]).fetchall()
            events = [dict(row) for row in rows]
    for item in events:
        item["occurred_at"] = iso_timestamp(item["occurred_at"])
        item["url"] = ("https://www.pinterest.com/pin/" + item["external_id"] + "/"
                       if item["platform"] == "pinterest" and str(item["external_id"]).isdigit()
                       else "https://thebookswanderer.com/products/" + quote(str(item["slug"]), safe="-_.~"))
    return {"day": day.isoformat(), "timezone": timezone,
            "start_utc": iso_timestamp(start), "end_utc_exclusive": iso_timestamp(end),
            "events": events, "total": total, "limit": limit, "offset": offset,
            "has_more": offset + len(events) < total,
            "coverage": {"store_tracking_started_at": started,
                         "store_ledger_available": "product_publication_events" in tables,
                         "pinterest_receipts_available": "pinterest_pins" in tables,
                         "limitations": ["Creation is not publication. Earlier store publication dates are unknown.",
                                         "Store receipts cover ORM visibility changes after tracking was installed; bulk SQL changes bypass tracking.",
                                         "Pinterest times are local receipt times, not first product publication dates.",
                                         "Etsy and other platforms are not included; query their listing metadata separately."]}}


@app.get("/suppliers/etsy/listings")
async def etsy_listings(state: Literal["active", "inactive", "draft", "sold_out", "expired"] = "active",
                        limit: int = Query(default=50, ge=1, le=100),
                        offset: int = Query(default=0, ge=0)):
    return await store_call("/suppliers/etsy/listings", {"state": state, "limit": limit, "offset": offset})

@app.get("/suppliers/cj/search")
async def cj_search(q: str = Query(min_length=2, max_length=100),
                    page: int = Query(default=1, ge=1, le=50),
                    size: int = Query(default=20, ge=1, le=50)):
    data = await cj_call("search_products", q.strip(), page=page, size=size)
    rows = []
    for bucket in (data.get("content") if isinstance(data, dict) else None) or []:
        if isinstance(bucket, dict) and isinstance(bucket.get("productList"), list):
            rows.extend(x for x in bucket["productList"] if isinstance(x, dict))
        elif isinstance(bucket, dict):
            rows.append(bucket)
    items = []
    for row in rows:
        pid = str(row.get("id") or row.get("pid") or "")
        if not re.fullmatch(CJ_ID, pid):
            continue
        items.append({
            "pid": pid,
            "sku": str(row.get("sku") or ""),
            "title": str(row.get("nameEn") or row.get("productNameEn") or ""),
            "cost_usd": number(row.get("sellPrice") or row.get("productSellPrice")),
            "image_url": str(row.get("bigImage") or row.get("productImage") or ""),
            "listed_num": int(number(row.get("listedNum"))),
            "has_video": bool(number(row.get("isVedio"))),
        })
    prices = await retail_prices(item["cost_usd"] for item in items)
    owned = owned_cj_pids({item["pid"] for item in items})
    for item in items:
        item["suggested_price_usd"] = prices.get(item["cost_usd"])
        item["in_store"] = item["pid"] in owned
    return {"query": q.strip(), "page": page, "products": items}

@app.get("/suppliers/cj/products/{pid}")
async def cj_product(pid: str = PathParam(pattern=CJ_ID)):
    data = await cj_call("get_product_details", pid=pid)
    if not isinstance(data, dict) or not data:
        raise HTTPException(404, "CJ product not found")
    variants = []
    for row in data.get("variants") or []:
        if not isinstance(row, dict):
            continue
        variants.append({
            "vid": str(row.get("vid") or ""),
            "sku": str(row.get("variantSku") or ""),
            "name": str(row.get("variantKey") or row.get("variantNameEn") or ""),
            "cost_usd": number(row.get("variantSellPrice")),
            "image_url": str(row.get("variantImage") or ""),
            "weight_g": number(row.get("variantWeight")),
        })
    prices = await retail_prices(v["cost_usd"] for v in variants)
    for variant in variants:
        variant["suggested_price_usd"] = prices.get(variant["cost_usd"])
    images = [str(u) for u in (data.get("productImageSet") or []) if u][:16]
    return {
        "pid": str(data.get("pid") or pid),
        "sku": str(data.get("productSku") or ""),
        "title": str(data.get("productNameEn") or ""),
        "category": str(data.get("categoryName") or ""),
        "images": images,
        "variants": variants[:100],
        "in_store": bool(owned_cj_pids({pid})),
    }

class Draft(BaseModel):
    pid: str = Field(pattern=CJ_ID)
    vid: str | None = Field(default=None, pattern=CJ_ID)
    title: str | None = Field(default=None, min_length=3, max_length=300)
    category: str = Field(default="", max_length=120)
    price_usd: float | None = Field(default=None, gt=0, le=10000)

class DraftEdit(BaseModel):
    lulu_package: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,40}$")
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    title_es: str | None = Field(default=None, min_length=3, max_length=300)
    description_es: str | None = Field(default=None, min_length=1, max_length=5000)
    category: str | None = Field(default=None, max_length=120)
    price_usd: float | None = Field(default=None, gt=0, le=10000)

class Confirmation(BaseModel):
    code: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")

class Publication(Confirmation):
    pin: bool = False

async def store_call(path, payload, preview=False):
    """The storefront does every write; this service never writes store.db."""
    key = credential("draft_key", "TBW_DRAFT_KEY_FILE")
    try:
        async with httpx.AsyncClient(
            timeout=60, follow_redirects=False, transport=store_transport
        ) as client:
            response = await client.post(
                STORE_API + "/api/internal" + path,
                params={"preview": "true"} if preview else None,
                headers={"Authorization": "Bearer " + key},
                json=payload,
            )
    except httpx.HTTPError:
        raise HTTPException(503, "Store unavailable") from None
    relayed = {400, 403, 404, 409, 422}
    if path.startswith("/crosslist/"):
        relayed.add(502)  # what Etsy or Printify answered; these messages carry no secrets
    if response.status_code in relayed:
        # The store's own messages (unknown draft, what blocks publication).
        try:
            detail = str(response.json().get("detail"))[:500]
        except (ValueError, AttributeError):
            detail = ""
        raise HTTPException(response.status_code, detail or "Store rejected the request")
    if response.status_code != 200:
        raise HTTPException(502 if response.status_code == 502 else 503,
                            "Store or CJ unavailable")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(503, "Invalid store response") from None
    if not isinstance(data, dict):
        raise HTTPException(503, "Invalid store response")
    return data

def new_draft(draft):
    return {
        "cj_pid": draft.pid, "cj_vid": draft.vid, "title": draft.title,
        "category": draft.category, "price_usd": draft.price_usd,
    }

@app.post("/drafts/preview")
async def draft_preview(draft: Draft):
    return await store_call("/drafts", new_draft(draft), preview=True)

@app.post("/drafts")
async def draft_create(draft: Draft):
    return await store_call("/drafts", new_draft(draft))

@app.post("/drafts/{product_id}/update")
async def draft_update(edit: DraftEdit, product_id: int = PathParam(ge=1)):
    return await store_call(
        f"/drafts/{product_id}/update", edit.model_dump(exclude_none=True)
    )

@app.post("/drafts/{product_id}/publish/preview")
async def draft_publish_preview(product_id: int = PathParam(ge=1)):
    return await store_call(f"/drafts/{product_id}/publish", None, preview=True)

@app.post("/drafts/{product_id}/publish")
async def draft_publish(publication: Publication, product_id: int = PathParam(ge=1)):
    return await store_call(f"/drafts/{product_id}/publish", publication.model_dump())

@app.post("/drafts/{product_id}/delete")
async def draft_delete(product_id: int = PathParam(ge=1)):
    return await store_call(f"/drafts/{product_id}/delete", None)

@app.post("/products/{product_id}/unpublish/preview")
async def unpublish_preview(product_id: int = PathParam(ge=1)):
    return await store_call(f"/products/{product_id}/unpublish", None, preview=True)

@app.post("/products/{product_id}/unpublish")
async def unpublish(confirmation: Confirmation, product_id: int = PathParam(ge=1)):
    return await store_call(
        f"/products/{product_id}/unpublish", {"code": confirmation.code}
    )

# Other suppliers: the storefront reads them with its own keys.

@app.get("/suppliers/printify/products")
async def printify_products(page: int = Query(default=1, ge=1, le=100),
                            limit: int = Query(default=20, ge=1, le=50)):
    return await store_call(
        "/suppliers/printify/products", {"page": page, "limit": limit}
    )

@app.get("/suppliers/printify/products/{printify_id}")
async def printify_product(printify_id: str = PathParam(pattern=r"^[A-Za-z0-9]{1,64}$")):
    return await store_call(f"/suppliers/printify/products/{printify_id}", None)

@app.get("/suppliers/prodigi/products/{sku}")
async def prodigi_product(sku: str = PathParam(pattern=r"^[A-Za-z0-9_-]{1,100}$")):
    return await store_call(f"/suppliers/prodigi/products/{sku}", None)

@app.get("/products/{product_id}/shipping")
async def shipping_quote(product_id: int = PathParam(ge=1),
                         country_code: str = Query(pattern=r"^[A-Za-z]{2}$"),
                         variant_id: int | None = Query(default=None, ge=1),
                         quantity: int = Query(default=1, ge=1, le=20)):
    return await store_call(f"/shipping/{product_id}", {
        "country_code": country_code, "variant_id": variant_id, "quantity": quantity,
    })

class SupplierCall(BaseModel):
    method: str = Field(pattern=r"^(GET|POST|PUT|PATCH|DELETE)$")
    path: str = Field(min_length=1, max_length=800)
    body: dict | list | None = None
    code: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")

@app.post("/suppliers/{supplier}/api")
async def supplier_call(call: SupplierCall,
                        supplier: str = PathParam(
                            pattern=r"^(cj|printify|lulu|prodigi|slant3d|etsy|meta|pinterest)$"),
                        preview: bool = Query(default=False)):
    """Any supplier API call, made by the storefront with its own key."""
    return await store_call(
        f"/suppliers/{supplier}/api", call.model_dump(), preview=preview
    )

class FromEtsy(BaseModel):
    listing_id: str = Field(pattern=r"^[0-9]{1,20}$")
    supplier: str | None = Field(default=None, pattern=r"^lulu$")
    code: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")

class ToEtsy(BaseModel):
    taxonomy_id: int | None = Field(default=None, ge=1)
    price_usd: float | None = Field(default=None, gt=0, le=10000)
    extra: dict[str, str | int | float | bool] | None = None
    code: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")

@app.post("/crosslist/from-etsy")
async def draft_from_etsy(body: FromEtsy, preview: bool = Query(default=False)):
    return await store_call("/crosslist/from-etsy", body.model_dump(), preview=preview)

@app.post("/crosslist/to-etsy/{product_id}")
async def publish_to_etsy(body: ToEtsy, product_id: int = PathParam(ge=1),
                          preview: bool = Query(default=False)):
    return await store_call(f"/crosslist/to-etsy/{product_id}", body.model_dump(), preview=preview)
