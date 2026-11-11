"""Qikink Sandbox only. No storefront hooks, wallet calls, or automatic order retries."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from io import BytesIO
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

SANDBOX_BASE = "https://sandbox.qikink.com"
DEFAULT_JOURNAL = Path(__file__).resolve().parents[1] / "data" / "qikink_sandbox.db"


class QikinkError(RuntimeError):
    """Safe to display: never contains response bodies, tokens, or request data."""


class DuplicateBlocked(QikinkError):
    pass


class OutcomeUnknown(QikinkError):
    pass


class ShippingAddress(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    first_name: str = Field(min_length=1, max_length=20)
    last_name: str = Field(default="", max_length=20)
    address1: str = Field(min_length=1, max_length=90)
    address2: str = Field(default="", max_length=90)
    phone: str = Field(min_length=1, max_length=15)
    email: str = Field(min_length=1, max_length=254)
    city: str = Field(min_length=1, max_length=40)
    zip: str = Field(pattern=r"^[0-9]{6}$")
    province: str = Field(min_length=1, max_length=40)
    # Current Sandbox test fixtures are limited to India.
    country_code: Literal["IN"] = "IN"


class PlainOrder(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reference: str = Field(pattern=r"^[a-z0-9_]{1,15}$")
    sku: str = Field(min_length=1, max_length=50)
    quantity: int = Field(default=1, ge=1, le=100, strict=True)
    price: str = "1"
    total_order_value: str = "1"
    shipping_address: ShippingAddress

    @field_validator("price", "total_order_value")
    @classmethod
    def numeric_amount(cls, value: str) -> str:
        from decimal import Decimal, InvalidOperation
        try:
            amount = Decimal(value)
        except InvalidOperation:
            raise ValueError("Amount must be numeric") from None
        if not amount.is_finite() or amount < 0:
            raise ValueError("Amount must be finite and non-negative")
        return format(amount, "f")

    def payload(self) -> dict:
        address = self.shipping_address.model_dump(exclude_defaults=True)
        address["country_code"] = self.shipping_address.country_code
        return {
            "order_number": self.reference,
            "qikink_shipping": "1",
            "gateway": "Prepaid",
            "total_order_value": self.total_order_value,
            "line_items": [{
                "search_from_my_products": 0,
                "print_type_id": "1",
                "quantity": str(self.quantity),
                "price": self.price,
                "sku": self.sku,
            }],
            "shipping_address": address,
        }


class PrintDesign(BaseModel):
    """Fully specified DTG design; blank fields for reused codes are not supported."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    design_code: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,20}$")
    width_inches: float = Field(default=2, gt=0, le=16, allow_inf_nan=False)
    height_inches: float = Field(default=2, gt=0, le=20, allow_inf_nan=False)
    placement_sku: Literal["fr", "bk", "lp", "rp", "rs", "ls"] = "fr"
    design_link: str = Field(min_length=1, max_length=512)
    mockup_link: str = Field(min_length=1, max_length=512)

    @field_validator("design_link", "mockup_link")
    @classmethod
    def public_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment):
            raise ValueError("Use a public HTTPS image URL without credentials, query or fragment")
        if parsed.hostname not in {"thebookswanderer.com", "www.thebookswanderer.com"} or parsed.port not in (None, 443):
            raise ValueError("Sandbox artwork must be hosted on the store domain")
        return value


class PrintedOrder(PlainOrder):
    design: PrintDesign

    def payload(self) -> dict:
        payload = super().payload()
        payload["line_items"][0]["designs"] = [self.design.model_dump()]
        return payload


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _order_id(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value)
    return text if text.isascii() and text.isdigit() and int(text) > 0 else None


class SandboxJournal:
    """Separate SQLite journal. Stores hashes, references and IDs, never addresses/tokens.

    pending/uncertain records must be reconciled manually; they are never retried.
    Atomic reservations protect multiple processes sharing this same database.
    """

    def __init__(self, path: Path = DEFAULT_JOURNAL):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS qikink_orders (
                account TEXT NOT NULL, reference TEXT NOT NULL, payload_hash TEXT NOT NULL,
                state TEXT NOT NULL, order_id TEXT, updated_at REAL NOT NULL,
                PRIMARY KEY (account, reference))""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def reserve(self, account: str, order: PlainOrder | PrintedOrder, known_id: str | None = None) -> dict:
        fingerprint = _digest(order.payload())
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload_hash, state, order_id FROM qikink_orders WHERE account=? AND reference=?",
                (account, order.reference),
            ).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise DuplicateBlocked("Reference already registered with a different payload")
                if row[1] == "created":
                    if known_id is not None and known_id != row[2]:
                        raise DuplicateBlocked("Reference already linked to a different order ID")
                    return {"state": "created", "order_id": row[2], "cached": True}
                if known_id is not None:
                    raise DuplicateBlocked("Existing reservation requires manual reconciliation")
                if row[1] != "not_sent":
                    raise DuplicateBlocked("Reference blocked; inspect the journal before any resubmission")
                db.execute("UPDATE qikink_orders SET state='pending', updated_at=? WHERE account=? AND reference=?",
                           (time.time(), account, order.reference))
            else:
                db.execute("INSERT INTO qikink_orders VALUES (?, ?, ?, ?, ?, ?)",
                           (account, order.reference, fingerprint,
                            "created" if known_id else "pending", known_id, time.time()))
        return {"state": "created" if known_id else "pending", "order_id": known_id, "cached": False}

    def finish(self, account: str, reference: str, state: str, order_id: str | None = None):
        with closing(self._connect()) as db, db:
            db.execute("UPDATE qikink_orders SET state=?, order_id=?, updated_at=? WHERE account=? AND reference=?",
                       (state, order_id, time.time(), account, reference))

    def get(self, account: str, reference: str) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT state, order_id FROM qikink_orders WHERE account=? AND reference=?",
                             (account, reference)).fetchone()
        return {"reference": reference, "state": row[0], "order_id": row[1]} if row else None


class SandboxClient:
    def __init__(self, client_id: str, client_secret: str, journal: SandboxJournal,
                 *, transport: httpx.AsyncBaseTransport | None = None):
        if os.getenv("QIKINK_ENV", "sandbox").strip().lower() != "sandbox":
            raise QikinkError("Only QIKINK_ENV=sandbox is supported")
        if not client_id.strip() or not client_secret.strip():
            raise QikinkError("Missing Qikink Sandbox credentials")
        self._client_id = client_id.strip()
        self._secret = client_secret.strip()
        self.account = hashlib.sha256(self._client_id.encode()).hexdigest()
        self.journal = journal
        self._http = httpx.AsyncClient(timeout=30, follow_redirects=False, transport=transport)
        self._token = ""
        self._expires = 0.0
        self._auth_lock = asyncio.Lock()

    @classmethod
    def from_env(cls, journal: SandboxJournal):
        return cls(os.getenv("QIKINK_SANDBOX_CLIENT_ID", ""),
                   os.getenv("QIKINK_SANDBOX_CLIENT_SECRET", ""), journal)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._http.aclose()

    async def authenticate(self) -> None:
        async with self._auth_lock:
            if self._token and self._expires > time.monotonic() + 30:
                return
            try:
                response = await self._http.post(SANDBOX_BASE + "/api/token", data={
                    "ClientId": self._client_id, "client_secret": self._secret,
                })
                if response.status_code != 200:
                    raise QikinkError(f"Sandbox authentication failed: HTTP {response.status_code}")
                data = response.json()
                token = data.get("Accesstoken")
                expires = int(data.get("expires_in", 3600))
                if not isinstance(token, str) or not token.strip() or expires <= 0:
                    raise ValueError
            except (httpx.HTTPError, ValueError, TypeError, AttributeError, OverflowError):
                raise QikinkError("Sandbox authentication unavailable or invalid response") from None
            self._token = token
            self._expires = time.monotonic() + expires

    async def create_plain_order(self, order: PlainOrder) -> dict:
        # Revalidate/copy so callers cannot change nested fields across awaits.
        order = PlainOrder.model_validate(order.model_dump())
        return await self._create_order(order)

    async def create_printed_order(self, order: PrintedOrder) -> dict:
        order = PrintedOrder.model_validate(order.model_dump())
        return await self._create_order(order)

    async def check_artwork(self, design: PrintDesign) -> None:
        """Read only store-hosted PNG/JPEG files; never forward Qikink headers."""
        try:
            for url in dict.fromkeys((design.design_link, design.mockup_link)):
                async with self._http.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response:
                    if response.status_code != 200:
                        raise ValueError
                    if response.headers.get("content-type", "").split(";")[0].strip().lower() not in {"image/png", "image/jpeg"}:
                        raise ValueError
                    image_bytes = bytearray()
                    async for chunk in response.aiter_bytes():
                        image_bytes.extend(chunk)
                        if len(image_bytes) > 4 * 1024 * 1024:
                            raise ValueError
                with Image.open(BytesIO(image_bytes)) as image:
                    if image.format not in {"PNG", "JPEG"} or image.width * image.height > 40_000_000:
                        raise ValueError
                    image.verify()
        except Exception:
            raise QikinkError("Artwork preflight failed; use accessible store-hosted PNG/JPEG files up to 4 MiB") from None

    async def _create_order(self, order: PlainOrder | PrintedOrder) -> dict:
        result = self.journal.reserve(self.account, order)
        if result["state"] == "created":
            return {**result, "reference": order.reference}
        try:
            if isinstance(order, PrintedOrder):
                await self.check_artwork(order.design)
            await self.authenticate()
        except BaseException:
            # Artwork/auth failed before any order request: retrying is safe.
            self.journal.finish(self.account, order.reference, "not_sent")
            raise
        try:
            response = await self._http.post(
                SANDBOX_BASE + "/api/order/create", json=order.payload(),
                headers={"ClientId": self._client_id, "Accesstoken": self._token},
            )
            if response.status_code == 400:
                self.journal.finish(self.account, order.reference, "rejected")
                raise QikinkError("Sandbox rejected the order (HTTP 400); no automatic retry")
            if response.status_code != 200:
                raise ValueError
            data = response.json()
            remote_id = _order_id(data.get("order_id"))
            if str(data.get("status_code")) != "200" or remote_id is None:
                raise ValueError
        except QikinkError:
            raise
        except BaseException as exc:
            self.journal.finish(self.account, order.reference, "uncertain")
            if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                raise
            raise OutcomeUnknown("Sandbox creation result unknown; do not resubmit") from None
        # If this commit fails, pending remains blocked. Never resend to recover it.
        self.journal.finish(self.account, order.reference, "created", remote_id)
        return {"state": "created", "order_id": remote_id, "reference": order.reference, "cached": False}

    def remember_existing(self, order: PlainOrder, order_id: str) -> dict:
        remote_id = _order_id(order_id)
        if remote_id is None:
            raise QikinkError("Invalid existing order ID")
        return self.journal.reserve(self.account, order, known_id=remote_id)

    async def lookup(self, order_id: str) -> dict:
        remote_id = _order_id(order_id)
        if remote_id is None:
            raise QikinkError("Invalid order ID")
        await self.authenticate()
        attempts = []
        for path in ("/api/order/list", "/api/order"):
            try:
                response = await self._http.get(SANDBOX_BASE + path,
                    params={"id": remote_id, "params": "order_id,number,status"},
                    headers={"ClientId": self._client_id, "Accesstoken": self._token})
                attempt = {"path": path, "http_status": response.status_code}
                attempts.append(attempt)
                if response.status_code != 200:
                    continue
                data = response.json()
                # Only documented top-level order or list/data envelope shapes.
                if isinstance(data, dict) and data.get("success") is False:
                    continue
                records = data.get("data", data) if isinstance(data, dict) else data
                records = [records] if isinstance(records, dict) else records
                if isinstance(records, list):
                    for record in records:
                        if isinstance(record, dict) and _order_id(record.get("order_id")) == remote_id:
                            return {"state": "found", "order_id": remote_id,
                                    "attempts": attempts}
            except (httpx.HTTPError, ValueError, TypeError):
                if not attempts or attempts[-1]["path"] != path:
                    attempts.append({"path": path})
                attempts[-1]["response_unavailable"] = True
        # Read failure never changes a successful creation journal record.
        return {"state": "unverified", "order_id": remote_id, "attempts": attempts}
