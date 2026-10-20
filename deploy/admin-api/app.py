"""Restricted administrative API: product reads and isolated Qikink drafts."""
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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

StoreImage = Annotated[str, StringConstraints(
    max_length=500,
    pattern=r"^https://(?:www\.)?thebookswanderer\.com/assets/[A-Za-z0-9_./%-]+\.(?:jpg|jpeg|png)$",
)]

class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    qikink_sku: str = Field(min_length=1, max_length=50)
    design_image: StoreImage | None = None
    mockup_image: StoreImage | None = None

class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reference: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    supplier: Literal["qikink"] = "qikink"
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    variants: list[Variant] = Field(min_length=1, max_length=40)

def journal():
    path = Path(os.getenv(
        "TBW_ADMIN_DRAFT_DB", "/var/lib/tbw-admin-api/drafts.sqlite3"
    ))
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            reference TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
            payload TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    connection.commit()
    return connection

def draft_result(row):
    return {
        "draft": json.loads(row["payload"]),
        "created_at": row["created_at"],
        "state": "draft",
        "public_sales_enabled": False,
        "order_submission_enabled": False,
        "pending": [
            "supplier_sku_and_artwork_verification",
            "destination_and_supplier_cost_verification",
            "retail_pricing_and_store_mapping",
        ],
    }

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
        "capabilities": ["products:read", "qikink-drafts:read", "qikink-drafts:write"],
        "order_submission_enabled": False,
        "product_publication_enabled": False,
    }

@app.get("/products")
def products(limit: int = Query(default=50, ge=1, le=100),
             offset: int = Query(default=0, ge=0)):
    path = Path(os.getenv(
        "TBW_ADMIN_STORE_DB",
        "/var/www/thebookswanderer.com/server/data/store.db",
    ))
    uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT id, slug, title, supplier, price_usd, active
            FROM products ORDER BY id LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    return {"products": [dict(row) for row in rows], "limit": limit, "offset": offset}


class CatalogVariant(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    qikink_sku: str = Field(min_length=1, max_length=50)
    sku_kind: Literal["product", "store"]
    product_title: str = Field(min_length=1, max_length=300)

class CatalogSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: Literal[1]
    source: str = Field(min_length=1, max_length=500)
    retrieved_at: datetime
    variants: list[CatalogVariant] = Field(max_length=10000)

@app.get("/qikink/catalog")
def qikink_catalog(
    query: str = Query(default="", max_length=200),
    sku: str | None = Query(default=None, min_length=1, max_length=50),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Read an operator-provided snapshot; never contact the supplier."""
    path = Path(os.getenv(
        "TBW_QIKINK_CATALOG_FILE", "/etc/tbw-admin-api/qikink-catalog.json"
    ))
    try:
        # Bound memory and reject incomplete, ambiguous or future-dated snapshots.
        with path.open("rb") as handle:
            raw = handle.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError
        snapshot = CatalogSnapshot.model_validate_json(raw)
        if (snapshot.retrieved_at.tzinfo is None
            or snapshot.retrieved_at > datetime.now(timezone.utc)
            or len({v.qikink_sku for v in snapshot.variants}) != len(snapshot.variants)):
            raise ValueError
    except (OSError, ValueError):
        raise HTTPException(503, "Qikink catalog snapshot unavailable or invalid") from None
    terms = query.casefold().split()
    matches = [v for v in snapshot.variants if
        (sku is None or v.qikink_sku == sku)
        and all(term in f"{v.product_title} {v.name} {v.qikink_sku}".casefold()
                for term in terms)]
    return {
        "source_mode": "operator_snapshot",
        "source": snapshot.source,
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "live_verified": False,
        "variants": [v.model_dump() for v in matches[offset:offset + limit]],
        "total": len(matches), "limit": limit, "offset": offset,
        "order_submission_enabled": False,
        "product_publication_enabled": False,
    }

@app.post("/drafts")
def create_draft(draft: Draft):
    if len({v.qikink_sku for v in draft.variants}) != len(draft.variants):
        raise HTTPException(422, "Duplicate Qikink SKU")
    payload = json.dumps(
        draft.model_dump(mode="json"), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False,
    )
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    with closing(journal()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM drafts WHERE reference=?", (draft.reference,)
        ).fetchone()
        created = row is None
        if row is not None and row["fingerprint"] != fingerprint:
            raise HTTPException(409, "Reference already used with different content")
        if created:
            db.execute(
                "INSERT INTO drafts VALUES (?, ?, ?, ?)",
                (draft.reference, fingerprint, payload,
                 datetime.now(timezone.utc).isoformat()),
            )
            row = db.execute(
                "SELECT * FROM drafts WHERE reference=?", (draft.reference,)
            ).fetchone()
    return JSONResponse(
        status_code=201 if created else 200,
        content=draft_result(row),
    )

@app.get("/drafts")
def drafts(limit: int = Query(default=50, ge=1, le=100),
           offset: int = Query(default=0, ge=0)):
    with closing(journal()) as db:
        rows = db.execute("""
            SELECT * FROM drafts ORDER BY created_at DESC, reference
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    return {"drafts": [draft_result(row) for row in rows]}

@app.get("/drafts/{reference}")
def get_draft(reference: str):
    with closing(journal()) as db:
        row = db.execute(
            "SELECT * FROM drafts WHERE reference=?", (reference,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Draft not found")
    return draft_result(row)
