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
            if request.method == "POST":
                return httpx2.Response(409, json={"private": key})
            return httpx2.Response(200, json={"products": []})
        bridge = AdminBridge(key, httpx2.MockTransport(handler))
        self.assertEqual(
            await bridge.request("GET", "/products"), {"products": []}
        )
        for method, path in [
            ("POST", "/orders"), ("GET", "/drafts/../products"),
            ("POST", "/products"),
        ]:
            with self.assertRaises(ToolError):
                await bridge.request(method, path)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ToolError) as error:
            await bridge.request("POST", "/drafts", payload={})
        self.assertNotIn(key, str(error.exception))
        self.assertNotIn("private", str(error.exception))

    async def test_catalog_tool_is_read_only_and_forwards_filters(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx2.Response(200, json={"variants": [], "live_verified": False})
        with tempfile.TemporaryDirectory() as temporary:
            server = create_server(config(), "a" * 40, temporary,
                                   httpx2.MockTransport(handler))
            async with Client(server) as client:
                tools = {tool.name: tool for tool in await client.list_tools()}
                self.assertTrue(tools["tbw_search_qikink_catalog"].annotations.readOnlyHint)
                await client.call_tool("tbw_search_qikink_catalog", {
                    "query": "bookmark", "sku": "FIXTURE-Classic", "limit": 5,
                })
                with self.assertRaises(ToolError):
                    await client.call_tool("tbw_search_qikink_catalog", {"limit": 101})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].method, "GET")
        self.assertEqual(calls[0].url.path, "/qikink/catalog")
        self.assertEqual(calls[0].url.params["sku"], "FIXTURE-Classic")
        self.assertEqual(calls[0].url.params["query"], "bookmark")
        bridge = AdminBridge("a" * 40, httpx2.MockTransport(handler))
        with self.assertRaises(ToolError):
            await bridge.request("POST", "/qikink/catalog")
        self.assertEqual(len(calls), 1)

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
                "tbw_list_qikink_drafts", "tbw_get_qikink_draft",
                "tbw_create_qikink_draft", "tbw_search_qikink_catalog",
            })
            serialized = json.dumps(
                [tool.model_dump(mode="json") for tool in tools]
            )
            self.assertNotIn("a" * 40, serialized)
            self.assertNotIn("s" * 40, serialized)

if __name__ == "__main__":
    unittest.main()
