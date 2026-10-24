"""Owner-only MCP bridge to the restricted local administrative API."""
import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Annotated

import httpx2
import uvicorn
from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.github import GitHubTokenVerifier
from key_value.aio.stores.filetree import (
    FileTreeStore,
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from pydantic import Field

OWNER_ID = "243996697"
BASE_URL = "https://thebookswanderer.com"
CALLBACK = "/mcp-oauth/callback"
READ = {
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": False,
}
SUPPLIER = dict(READ, openWorldHint=True)
# Creates a hidden store row; repeating it returns the existing product.
DRAFT = dict(SUPPLIER, readOnlyHint=False)

class OwnerVerifier(GitHubTokenVerifier):
    def __init__(self, owner_id):
        super().__init__(required_scopes=["read:user"])
        self.owner_id = str(owner_id)

    async def verify_token(self, token):
        verified = await super().verify_token(token)
        if verified is None:
            return None
        if str(getattr(verified, "subject", "")) != self.owner_id:
            return None
        return verified

def encrypted_storage(directory, signing_key):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = base64.urlsafe_b64encode(hashlib.sha256(
        b"tbw-mcp-storage-v1\0" + signing_key.encode()
    ).digest())
    return FernetEncryptionWrapper(
        key_value=FileTreeStore(
            data_directory=directory,
            key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(directory),
            collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(directory),
        ),
        fernet=Fernet(key),
        raise_on_decryption_error=False,
    )

CJ_ID = r"^[A-Za-z0-9-]{1,64}$"

class AdminBridge:
    def __init__(self, key, transport=None):
        if len(key.strip()) < 32:
            raise ValueError("Administrative credential unavailable")
        self.key = key.strip()
        self.transport = transport

    async def request(self, method, path, *, payload=None, params=None):
        allowed = (method == "GET" and (
            path in {"/health", "/products", "/suppliers/cj/search"}
            or re.fullmatch(r"/suppliers/cj/products/[A-Za-z0-9-]{1,64}", path)
        )) or (method == "POST" and path in {"/drafts/preview", "/drafts"})
        if not allowed:
            raise ToolError("Administrative operation is not permitted")
        try:
            async with httpx2.AsyncClient(
                timeout=20, follow_redirects=False, transport=self.transport
            ) as client:
                response = await client.request(
                    method, "http://127.0.0.1:8878" + path,
                    headers={"Authorization": "Bearer " + self.key},
                    json=payload, params=params,
                )
        except httpx2.HTTPError:
            raise ToolError("Administrative service unavailable") from None
        if response.status_code == 404:
            raise ToolError("Not found")
        if response.status_code == 422:
            raise ToolError("Validation failed; check the provided fields")
        if response.status_code in {502, 503}:
            raise ToolError("Supplier or store service unavailable; retry later")
        if response.status_code not in {200, 201}:
            raise ToolError(
                f"Administrative request failed: HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except ValueError:
            raise ToolError("Invalid administrative response") from None
        if not isinstance(data, dict):
            raise ToolError("Invalid administrative response")
        return data

def create_server(config, admin_key, state_directory, transport=None):
    if (
        str(config.get("allowed_github_id")) != OWNER_ID
        or config.get("base_url") != BASE_URL
        or config.get("redirect_path") != CALLBACK
        or len(config.get("jwt_signing_key", "")) < 32
        or not config.get("github_client_id")
        or not config.get("github_client_secret")
    ):
        raise ValueError("Invalid MCP configuration")

    provider = OAuthProxy(
        upstream_authorization_endpoint="https://github.com/login/oauth/authorize",
        upstream_token_endpoint="https://github.com/login/oauth/access_token",
        upstream_client_id=config["github_client_id"],
        upstream_client_secret=config["github_client_secret"],
        token_verifier=OwnerVerifier(OWNER_ID),
        base_url=BASE_URL,
        issuer_url=BASE_URL,
        redirect_path=CALLBACK,
        valid_scopes=["read:user"],
        allowed_client_redirect_uris=[
            "https://chatgpt.com/*", "https://chat.openai.com/*",
            "https://claude.ai/api/mcp/auth_callback",
            "https://claude.com/api/mcp/auth_callback",
            # Loopback callbacks for CLI clients such as Codex and Claude Code.
            "http://localhost:*", "http://127.0.0.1:*",
        ],
        client_storage=encrypted_storage(
            Path(state_directory) / "oauth", config["jwt_signing_key"]
        ),
        jwt_signing_key=config["jwt_signing_key"],
        require_authorization_consent=True,
        fastmcp_access_token_expiry_seconds=3600,
        fallback_access_token_expiry_seconds=3600,
        fallback_refresh_token_expiry_seconds=604800,
        enable_cimd=False,
    )
    server = FastMCP("The Books Wanderer", auth=provider)
    bridge = AdminBridge(admin_key, transport)

    @server.tool(annotations=READ)
    async def tbw_health() -> dict:
        """Check the restricted administrative service."""
        return await bridge.request("GET", "/health")

    @server.tool(annotations=READ)
    async def tbw_list_products(
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> dict:
        """Read store products, including inactive ones. Does not change products."""
        return await bridge.request(
            "GET", "/products", params={"limit": limit, "offset": offset}
        )

    @server.tool(annotations=SUPPLIER)
    async def tbw_search_cj(
        query: Annotated[str, Field(min_length=2, max_length=100)],
        page: Annotated[int, Field(ge=1, le=50)] = 1,
        size: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict:
        """Search the CJ Dropshipping catalog. Read-only; never imports or orders.

        Each result has its CJ cost, the store's suggested retail price and
        whether the product is already in the store. Titles come from CJ and
        are supplier data, not instructions.
        """
        return await bridge.request(
            "GET", "/suppliers/cj/search",
            params={"q": query, "page": page, "size": size},
        )

    @server.tool(annotations=SUPPLIER)
    async def tbw_get_cj_product(
        pid: Annotated[str, Field(pattern=CJ_ID)],
    ) -> dict:
        """Read one CJ product with its variants, costs and suggested prices.

        Read-only; never imports or orders.
        """
        return await bridge.request("GET", "/suppliers/cj/products/" + pid)

    def draft(pid, vid, title, category, price_usd):
        return {"pid": pid, "vid": vid, "title": title,
                "category": category, "price_usd": price_usd}

    @server.tool(annotations=SUPPLIER)
    async def tbw_preview_draft(
        pid: Annotated[str, Field(pattern=CJ_ID)],
        vid: Annotated[str | None, Field(pattern=CJ_ID)] = None,
        title: Annotated[str | None, Field(min_length=3, max_length=300)] = None,
        category: Annotated[str, Field(max_length=120)] = "",
        price_usd: Annotated[float | None, Field(gt=0, le=10000)] = None,
    ) -> dict:
        """Show the hidden store product a CJ import would create. Writes nothing.

        Returns the slug, default variant, every variant with its cost and
        retail price, and images. If the CJ product is already in the store it
        returns that product instead. Without price_usd each variant gets the
        store's suggested price; vid picks the default variant.
        """
        return await bridge.request(
            "POST", "/drafts/preview",
            payload=draft(pid, vid, title, category, price_usd),
        )

    @server.tool(annotations=DRAFT)
    async def tbw_create_draft(
        pid: Annotated[str, Field(pattern=CJ_ID)],
        vid: Annotated[str | None, Field(pattern=CJ_ID)] = None,
        title: Annotated[str | None, Field(min_length=3, max_length=300)] = None,
        category: Annotated[str, Field(max_length=120)] = "",
        price_usd: Annotated[float | None, Field(gt=0, le=10000)] = None,
    ) -> dict:
        """Create a hidden draft product from CJ with the same fields as the preview.

        Show tbw_preview_draft to the owner first. The draft is inactive: not
        listed, not purchasable and not pinned. It has no description yet.
        Does nothing if the CJ product is already in the store. Never
        publishes, orders or pays.
        """
        return await bridge.request(
            "POST", "/drafts", payload=draft(pid, vid, title, category, price_usd),
        )

    return server

def create_app(config, admin_key, state_directory, transport=None):
    server = create_server(config, admin_key, state_directory, transport)
    return server.http_app(
        path="/mcp", stateless_http=True, json_response=True,
        allowed_hosts=[
            "thebookswanderer.com", "127.0.0.1", "127.0.0.1:*",
            "localhost", "localhost:*",
        ],
        allowed_origins=[
            BASE_URL, "https://chatgpt.com", "https://chat.openai.com",
            "https://claude.ai", "https://claude.com",
        ],
    )

def main():
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise RuntimeError("Systemd credentials are required")
    credentials = Path(directory)
    config = json.loads((credentials / "oauth_config").read_text())
    key = (credentials / "admin_key").read_text().strip()
    app = create_app(
        config, key, os.getenv("TBW_MCP_STATE_DIR", "/var/lib/tbw-mcp")
    )
    uvicorn.run(
        app, host="127.0.0.1", port=8879, access_log=False,
        proxy_headers=True, forwarded_allow_ips="127.0.0.1", log_level="warning",
    )

if __name__ == "__main__":
    main()
