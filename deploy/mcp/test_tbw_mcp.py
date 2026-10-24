import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx2
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.github import GitHubTokenVerifier
from tbw_mcp import (
    AdminBridge, BASE_URL, CALLBACK, OWNER_ID, OwnerVerifier,
    create_app, create_server, encrypted_storage,
)

def config():
    return {
        "allowed_github_id": OWNER_ID,
        "base_url": BASE_URL,
        "redirect_path": CALLBACK,
        "github_client_id": "offline-client",
        "github_client_secret": "s" * 40,
        "jwt_signing_key": "k" * 64,
    }

class McpTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_gate(self):
        verifier = OwnerVerifier(OWNER_ID)
        for subject, allowed in [(OWNER_ID, True), ("999", False), (None, False)]:
            upstream = SimpleNamespace(subject=subject)
            with patch.object(
                GitHubTokenVerifier, "verify_token",
                new=AsyncMock(return_value=upstream),
            ):
                result = await verifier.verify_token("offline-token")
                self.assertEqual(result is not None, allowed)
        with patch.object(
            GitHubTokenVerifier, "verify_token", new=AsyncMock(return_value=None)
        ):
            self.assertIsNone(await verifier.verify_token("offline-token"))

    async def test_bridge_restrictions_and_safe_errors(self):
        calls = []
        key = "a" * 40
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, "127.0.0.1")
            self.assertEqual(request.url.port, 8878)
            self.assertEqual(request.headers["Authorization"], "Bearer " + key)
            if request.url.path.startswith("/suppliers/"):
                return httpx2.Response(502, json={"private": key})
            return httpx2.Response(200, json={"products": []})
        bridge = AdminBridge(key, httpx2.MockTransport(handler))
        self.assertEqual(
            await bridge.request("GET", "/products"), {"products": []}
        )
        for method, path in [
            ("POST", "/orders"), ("GET", "/suppliers/cj/products/../x"),
            ("POST", "/products"), ("POST", "/drafts"), ("GET", "/drafts"),
        ]:
            with self.assertRaises(ToolError):
                await bridge.request(method, path)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ToolError) as error:
            await bridge.request("GET", "/suppliers/cj/search", params={"q": "x"})
        self.assertNotIn(key, str(error.exception))
        self.assertNotIn("private", str(error.exception))

    async def test_encrypted_persistent_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = encrypted_storage(directory, "k" * 64)
            await store.put(
                "offline-key", {"token": "offline-sensitive-fixture"},
                collection="tests",
            )
            reopened = encrypted_storage(directory, "k" * 64)
            result = await reopened.get("offline-key", collection="tests")
            self.assertEqual(result["token"], "offline-sensitive-fixture")
            for path in directory.rglob("*"):
                if path.is_file():
                    self.assertNotIn(
                        b"offline-sensitive-fixture", path.read_bytes()
                    )

    async def test_discovery_and_protected_endpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = create_app(config(), "a" * 40, temporary)
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url=BASE_URL,
            ) as client:
                response = await client.get(
                    "/.well-known/oauth-authorization-server"
                )
                self.assertEqual(response.status_code, 200)
                metadata = response.json()
                self.assertEqual(metadata["issuer"].rstrip("/"), BASE_URL)
                self.assertIn("read:user", metadata["scopes_supported"])
                response = await client.get(
                    "/mcp", headers={"Accept": "application/json, text/event-stream"}
                )
                self.assertEqual(response.status_code, 405)
                for authorization in (None, "Bearer offline-invalid-token"):
                    headers = {"Accept": "application/json, text/event-stream"}
                    if authorization:
                        headers["Authorization"] = authorization
                    response = await client.post(
                        "/mcp",
                        headers=headers,
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2025-03-26",
                                "capabilities": {},
                                "clientInfo": {"name": "offline-test", "version": "1"},
                            },
                        },
                    )
                    self.assertEqual(response.status_code, 401)
                    self.assertIn(
                        "resource_metadata", response.headers["www-authenticate"]
                    )

    async def test_exact_tool_surface(self):
        with tempfile.TemporaryDirectory() as temporary:
            server = create_server(config(), "a" * 40, temporary)
            async with Client(server) as client:
                tools = await client.list_tools()
            self.assertEqual({tool.name for tool in tools}, {
                "tbw_health", "tbw_list_products",
                "tbw_search_cj", "tbw_get_cj_product",
            })
            for tool in tools:
                self.assertTrue(tool.annotations.read_only_hint)
            serialized = json.dumps(
                [tool.model_dump(mode="json") for tool in tools]
            )
            self.assertNotIn("a" * 40, serialized)
            self.assertNotIn("s" * 40, serialized)

    async def test_client_redirects(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = create_app(config(), "a" * 40, temporary)
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url=BASE_URL,
            ) as client:
                for uri, allowed in [
                    ("https://claude.ai/api/mcp/auth_callback", True),
                    ("https://chatgpt.com/connector_platform_oauth_redirect", True),
                    ("http://localhost:1455/auth/callback", True),
                    ("http://127.0.0.1:33418/callback", True),
                    ("https://evil.example/callback", False),
                    ("http://localhost@evil.example/callback", False),
                ]:
                    response = await client.post("/register", json={
                        "redirect_uris": [uri], "client_name": "offline",
                        "token_endpoint_auth_method": "none",
                        "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"],
                    })
                    self.assertEqual(response.status_code < 300, allowed, uri)

if __name__ == "__main__":
    unittest.main()
