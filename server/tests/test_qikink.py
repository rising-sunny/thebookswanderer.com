"""Qikink Sandbox contract and duplicate protection; all HTTP calls are mocked."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.qikink import (DuplicateBlocked, OutcomeUnknown, PlainOrder, QikinkError,
                              SandboxClient, SandboxJournal)

ADDRESS = {
    "first_name": "Sandbox", "last_name": "Test", "address1": "Sandbox test address",
    "phone": "9876543210", "email": "sandbox@example.com", "city": "Coimbatore",
    "zip": "641001", "province": "Tamil Nadu", "country_code": "IN",
}


def order(reference="tbw_test", **extra):
    return PlainOrder(reference=reference, sku="MVnHs-Wh-S", shipping_address=ADDRESS, **extra)


class QikinkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sandbox.db"
        self.journal = SandboxJournal(self.path)
        self.calls = []
        env = patch.dict(os.environ, {"QIKINK_ENV": "sandbox", "QIKINK_BASE_URL": "https://api.qikink.com"})
        env.start()
        self.addCleanup(env.stop)

    def client(self, handler=None):
        async def respond(request):
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(request.url.host, "sandbox.qikink.com")
            self.calls.append(request.url.path)
            if handler:
                reply = handler(request)
                return await reply if asyncio.iscoroutine(reply) else reply
            if request.url.path == "/api/token":
                self.assertIn(b"ClientId=test-client", request.content)
                self.assertIn(b"client_secret=test-secret", request.content)
                return httpx.Response(200, json={"Accesstoken": "private-token", "expires_in": 3600})
            self.assertEqual(request.url.path, "/api/order/create")
            payload = json.loads(request.content)
            self.assertEqual(request.headers["Accesstoken"], "private-token")
            self.assertEqual(payload["gateway"], "Prepaid")
            self.assertEqual(payload["line_items"][0]["print_type_id"], "1")
            self.assertNotIn("designs", payload["line_items"][0])
            return httpx.Response(200, json={"status_code": "200", "order_id": 24616032})
        return SandboxClient("test-client", "test-secret", self.journal, transport=httpx.MockTransport(respond))

    async def test_creation_survives_client_and_journal_restart_without_resending(self):
        async with self.client() as client:
            result = await client.create_plain_order(order())
        self.assertEqual(result["order_id"], "24616032")
        self.assertFalse(result["cached"])
        self.journal = SandboxJournal(self.path)
        async with self.client() as client:
            again = await client.create_plain_order(order())
        self.assertTrue(again["cached"])
        self.assertEqual(self.calls, ["/api/token", "/api/order/create"])
        saved = self.path.read_bytes()
        for secret in (b"private-token", b"test-secret", b"sandbox@example.com", b"Sandbox test address"):
            self.assertNotIn(secret, saved)

    async def test_changed_payload_cannot_reuse_reference(self):
        async with self.client() as client:
            await client.create_plain_order(order())
            with self.assertRaises(DuplicateBlocked):
                await client.create_plain_order(order(quantity=2))
        self.assertEqual(self.calls.count("/api/order/create"), 1)

    async def test_timeout_is_persistently_uncertain_without_automatic_retry(self):
        def respond(request):
            if request.url.path == "/api/token":
                return httpx.Response(200, json={"Accesstoken": "private-token"})
            raise httpx.ReadTimeout("private-token test-secret")
        async with self.client(respond) as client:
            with self.assertRaises(OutcomeUnknown) as caught:
                await client.create_plain_order(order())
            self.assertNotIn("private-token", str(caught.exception))
            self.assertEqual(self.journal.get(client.account, "tbw_test")["state"], "uncertain")
        self.journal = SandboxJournal(self.path)
        async with self.client() as client:
            with self.assertRaises(DuplicateBlocked):
                await client.create_plain_order(order())
        self.assertEqual(self.calls.count("/api/order/create"), 1)

    async def test_validation_rejection_stays_blocked_and_does_not_disclose_body(self):
        def respond(request):
            if request.url.path == "/api/token":
                return httpx.Response(200, json={"Accesstoken": "private-token"})
            return httpx.Response(400, json={"error": "test-secret private-token"})
        async with self.client(respond) as client:
            with self.assertRaises(QikinkError) as caught:
                await client.create_plain_order(order())
            self.assertNotIn("test-secret", str(caught.exception))
            self.assertEqual(self.journal.get(client.account, "tbw_test")["state"], "rejected")
            with self.assertRaises(DuplicateBlocked):
                await client.create_plain_order(order())
        self.assertEqual(self.calls.count("/api/order/create"), 1)

    async def test_ambiguous_creation_responses_are_not_retried(self):
        for index, response in enumerate([
            httpx.Response(500), httpx.Response(302, headers={"Location": "https://api.qikink.com"}),
            httpx.Response(200, text="not json"), httpx.Response(200, json={"status_code": "200"}),
            httpx.Response(200, json={"status_code": "400", "order_id": 123}),
            httpx.Response(200, json={"status_code": "200", "order_id": True}),
        ]):
            def respond(request):
                return (httpx.Response(200, json={"Accesstoken": "private-token"})
                        if request.url.path == "/api/token" else response)
            async with self.client(respond) as client:
                with self.assertRaises(OutcomeUnknown):
                    await client.create_plain_order(order(f"case_{index}"))
                with self.assertRaises(DuplicateBlocked):
                    await client.create_plain_order(order(f"case_{index}"))
        self.assertEqual(self.calls.count("/api/order/create"), 6)

    async def test_failure_before_submission_can_be_safely_retried(self):
        def respond(request):
            return httpx.Response(200, json={"Accesstoken": "", "error": "test-secret"})
        async with self.client(respond) as client:
            with self.assertRaises(QikinkError):
                await client.create_plain_order(order())
            self.assertEqual(self.journal.get(client.account, "tbw_test")["state"], "not_sent")
        async with self.client() as client:
            self.assertEqual((await client.create_plain_order(order()))["state"], "created")
        self.assertEqual(self.calls.count("/api/order/create"), 1)

    async def test_concurrent_clients_share_atomic_reservations(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        async def respond(request):
            if request.url.path == "/api/token":
                return httpx.Response(200, json={"Accesstoken": "private-token"})
            entered.set()
            await release.wait()
            return httpx.Response(200, json={"status_code": "200", "order_id": 123})
        async with self.client(respond) as first, self.client() as second:
            second.journal = SandboxJournal(self.path)
            pending = asyncio.create_task(first.create_plain_order(order()))
            await asyncio.wait_for(entered.wait(), timeout=2)
            try:
                with self.assertRaises(DuplicateBlocked):
                    await second.create_plain_order(order())
            finally:
                release.set()
                await pending
        self.assertEqual(self.calls.count("/api/order/create"), 1)

    async def test_token_is_reused_until_expiry(self):
        async with self.client() as client:
            await client.create_plain_order(order("one"))
            await client.create_plain_order(order("two"))
            self.assertEqual(self.calls.count("/api/token"), 1)
            client._expires = 0
            await client.create_plain_order(order("three"))
        self.assertEqual(self.calls.count("/api/token"), 2)

    async def test_manual_existing_order_blocks_submission_without_network(self):
        async with self.client() as client:
            client.remember_existing(order("tbw_9ba7265277"), "24616032")
            result = await client.create_plain_order(order("tbw_9ba7265277"))
            self.assertTrue(result["cached"])
            with self.assertRaises(DuplicateBlocked):
                client.remember_existing(order("tbw_9ba7265277"), "999")
        self.assertEqual(self.calls, [])

    async def test_read_failure_preserves_confirmed_creation(self):
        async with self.client() as client:
            client.remember_existing(order(), "24616032")
            account = client.account
        def respond(request):
            if request.url.path == "/api/token":
                return httpx.Response(200, json={"Accesstoken": "private-token"})
            return httpx.Response(404 if request.url.path.endswith("list") else 500)
        async with self.client(respond) as client:
            result = await client.lookup("24616032")
        self.assertEqual(result["state"], "unverified")
        self.assertEqual([a["http_status"] for a in result["attempts"]], [404, 500])
        self.assertEqual(self.journal.get(account, "tbw_test")["state"], "created")
        self.assertNotIn("/api/order/create", self.calls)

    async def test_http_200_alone_does_not_confirm_order_lookup(self):
        for body in ({"success": True, "data": []}, {"data": [{"order_id": "999"}]},
                     {"success": False, "data": [{"order_id": "24616032"}]}):
            def respond(request):
                return (httpx.Response(200, json={"Accesstoken": "private-token"})
                        if request.url.path == "/api/token" else httpx.Response(200, json=body))
            async with self.client(respond) as client:
                self.assertEqual((await client.lookup("24616032"))["state"], "unverified")

    async def test_lookup_requires_matching_order_id(self):
        def respond(request):
            return (httpx.Response(200, json={"Accesstoken": "private-token"})
                    if request.url.path == "/api/token" else
                    httpx.Response(200, json={"success": True, "data": [{"order_id": 24616032}]}))
        async with self.client(respond) as client:
            self.assertEqual((await client.lookup("24616032"))["state"], "found")
        self.assertNotIn("/api/order/create", self.calls)

    async def test_payload_is_snapshotted_before_authentication(self):
        original = order()
        async def respond(request):
            if request.url.path == "/api/token":
                original.shipping_address.city = "Changed during authentication"
                return httpx.Response(200, json={"Accesstoken": "private-token"})
            self.assertEqual(json.loads(request.content)["shipping_address"]["city"], "Coimbatore")
            return httpx.Response(200, json={"status_code": "200", "order_id": 1})
        async with self.client(respond) as client:
            await client.create_plain_order(original)

    def test_live_mode_is_refused(self):
        with patch.dict(os.environ, {"QIKINK_ENV": "live"}):
            with self.assertRaises(QikinkError):
                self.client()

    def test_invalid_orders_fail_before_network(self):
        for change in ({"reference": "TOO-LONG-REFERENCE"}, {"quantity": 0}, {"quantity": True},
                       {"quantity": 101}, {"price": "NaN"}, {"total_order_value": "-1"}):
            data = order().model_dump() | change
            with self.assertRaises(ValidationError):
                PlainOrder.model_validate(data)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
