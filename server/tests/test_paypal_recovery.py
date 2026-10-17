"""Offline payment regressions: no PayPal, supplier, email or metrics calls."""
import asyncio
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import main
from database import Base
from models import Order, OrderItem, Product
from services import paypal, paypal_recovery as recovery, meta_capi, live_events

PPID = "9P12345678901234A"
APPROVED = {"id": PPID, "intent": "CAPTURE", "status": "APPROVED", "purchase_units": [
    {"reference_id": "1", "custom_id": "tbw:1", "amount": {"currency_code": "USD", "value": "25.00"}}]}
COMPLETED = copy.deepcopy(APPROVED)
COMPLETED["status"] = "COMPLETED"
COMPLETED["purchase_units"][0]["payments"] = {"captures": [
    {"id": "CAPTURE1", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "25.00"}}]}
APPROVAL_EVENT = {"id": "EVENT1", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": PPID}}
CAPTURE_EVENT = {"id": "EVENT2", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {
    "supplementary_data": {"related_ids": {"order_id": PPID}}}}


class Recovery(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.engine = create_engine("sqlite:///" + str(Path(tmp.name) / "orders.db"), connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose); Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.db = self.sessions(); self.addCleanup(self.db.close)
        self.order = Order(status="awaiting_payment", paypal_order_id=PPID, grand_total=25, email="test@example.invalid")
        self.product = Product(slug="test-book", title="Test book", supplier="lulu")
        self.db.add_all([self.order, self.product]); self.db.commit()
        self.db.add(OrderItem(order_id=1, product_id=self.product.id, quantity=1)); self.db.commit()
        def dependency():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[main.get_db] = dependency
        self.addCleanup(main.app.dependency_overrides.pop, main.get_db, None)
        def mock(obj, name, value):
            p = patch.object(obj, name, value); result = p.start(); self.addCleanup(p.stop); return result
        self.get = mock(paypal, "get_order", AsyncMock(return_value=copy.deepcopy(COMPLETED)))
        self.capture = mock(paypal, "capture_order", AsyncMock(return_value=copy.deepcopy(COMPLETED)))
        self.verify = mock(paypal, "verify_webhook", AsyncMock(return_value=True))
        mock(paypal, "PAYPAL_WEBHOOK_ID", "STORE-HOOK")
        mock(paypal, "configured", Mock(return_value=True))
        self.fulfil = mock(main, "_fulfil", AsyncMock())
        self.mail = mock(main.email_service, "send_order_paid", AsyncMock())
        self.metrics = mock(live_events, "record_purchase", Mock())
        self.meta = mock(meta_capi, "send_purchase", AsyncMock())

    async def request(self, method, path, **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="https://store.invalid") as c:
            return await c.request(method, path, **kwargs)

    def webhook(self, event=APPROVAL_EVENT):
        return asyncio.run(self.request("POST", "/api/webhooks/paypal", json=event))

    def complete(self):
        return asyncio.run(main._complete_paypal_order(self.order, self.db))

    def test_approval_captures_and_fulfils_without_browser(self):
        self.get.side_effect = [copy.deepcopy(APPROVED), copy.deepcopy(COMPLETED)]
        self.assertEqual(self.webhook().json()["status"], "success")
        self.capture.assert_awaited_once_with(PPID); self.fulfil.assert_awaited_once(); self.mail.assert_awaited_once()
        self.metrics.assert_called_once(); self.assertIsNone(self.meta.await_args.kwargs["client_ip"])
        self.assertIsNone(self.meta.await_args.kwargs["user_agent"])

    def test_completed_event_recovers_without_second_capture(self):
        self.assertEqual(self.webhook(CAPTURE_EVENT).json()["status"], "success")
        self.capture.assert_not_awaited(); self.fulfil.assert_awaited_once()

    def test_duplicate_and_out_of_order_events_and_return_do_not_repeat(self):
        self.assertEqual(self.webhook(CAPTURE_EVENT).json()["status"], "success")
        self.assertEqual(self.webhook().json()["status"], "already_paid")
        response = asyncio.run(self.request("GET", f"/api/checkout/return?order_id=1&token={PPID}"))
        self.assertIn("status=already_paid", response.headers["location"])
        self.fulfil.assert_awaited_once(); self.mail.assert_awaited_once(); self.metrics.assert_called_once()

    def test_bad_signature_cannot_trigger_any_payment_lookup(self):
        self.verify.return_value = False
        self.assertEqual(self.webhook().status_code, 403)
        self.get.assert_not_awaited(); self.capture.assert_not_awaited(); self.fulfil.assert_not_awaited()

    def test_signature_service_outage_requests_retry(self):
        self.verify.side_effect = TimeoutError("not logged")
        self.assertEqual(self.webhook().status_code, 503); self.get.assert_not_awaited()

    def test_foreign_store_event_is_ignored(self):
        event = copy.deepcopy(APPROVAL_EVENT); event["resource"]["id"] = "FOREIGNORDER12345"
        self.assertEqual(self.webhook(event).json()["status"], "ignored"); self.get.assert_not_awaited()

    def test_nonunique_local_mapping_is_held(self):
        self.db.add(Order(paypal_order_id=PPID)); self.db.commit()
        self.assertEqual(self.webhook().json()["status"], "ignored"); self.capture.assert_not_awaited()

    def test_unknown_event_is_ignored(self):
        self.assertEqual(self.webhook({"event_type": "PAYMENT.CAPTURE.PENDING"}).json()["status"], "ignored")
        self.get.assert_not_awaited()

    def test_malformed_and_oversized_bodies_are_rejected(self):
        for body, code in ((b"{bad", 400), (b"[]", 400), (b"x" * 262145, 413)):
            response = asyncio.run(self.request("POST", "/api/webhooks/paypal", content=body))
            self.assertEqual(response.status_code, code)
        self.verify.assert_not_awaited()

    def test_provider_lookup_failure_requests_retry_without_payment_side_effects(self):
        self.get.side_effect = TimeoutError()
        self.assertEqual(self.webhook().status_code, 503); self.fulfil.assert_not_awaited()
        self.db.refresh(self.order); self.assertEqual(self.order.status, "awaiting_payment")

    def test_lost_capture_response_is_reconciled(self):
        self.get.side_effect = [copy.deepcopy(APPROVED), copy.deepcopy(COMPLETED)]
        self.capture.side_effect = TimeoutError("private body")
        self.assertEqual(self.complete(), "success"); self.capture.assert_awaited_once()

    def test_unconfirmed_lost_capture_keeps_order_recoverable(self):
        self.get.return_value = copy.deepcopy(APPROVED); self.capture.side_effect = TimeoutError()
        self.assertEqual(self.webhook().status_code, 503)
        self.db.refresh(self.order); self.assertEqual(self.order.status, "awaiting_payment")
        self.fulfil.assert_not_awaited()

    def test_unapproved_order_is_not_captured(self):
        self.get.return_value = dict(APPROVED, status="CREATED")
        self.assertEqual(self.complete(), "payment_incomplete"); self.capture.assert_not_awaited()

    def test_identity_reference_currency_and_amount_validated_before_capture(self):
        cases = []
        for field, value in (("id", "WRONG"), ("intent", "AUTHORIZE")):
            data = copy.deepcopy(APPROVED); data[field] = value; cases.append(data)
        for field, value in (("reference_id", "2"), ("custom_id", "other:1"), ("amount", {"currency_code": "EUR", "value": "25.00"}), ("amount", {"currency_code": "USD", "value": "24.99"}), ("amount", {"currency_code": "USD", "value": "NaN"})):
            data = copy.deepcopy(APPROVED); data["purchase_units"][0][field] = value; cases.append(data)
        data = copy.deepcopy(APPROVED); data["purchase_units"] *= 2; cases.append(data)
        for data in cases:
            with self.subTest(data=data):
                self.get.return_value = data; self.assertEqual(self.complete(), "payment_incomplete")
        self.capture.assert_not_awaited(); self.fulfil.assert_not_awaited()

    def test_incomplete_partial_refunded_or_mismatched_capture_not_released(self):
        for change in ({"status": "PENDING"}, {"status": "REFUNDED"}, {"amount": {"currency_code": "USD", "value": "20.00"}}, {"custom_id": "tbw:2"}, {"id": ""}):
            data = copy.deepcopy(COMPLETED); data["purchase_units"][0]["payments"]["captures"][0].update(change)
            self.get.return_value = data; self.assertEqual(self.complete(), "payment_incomplete")
        self.capture.assert_not_awaited(); self.fulfil.assert_not_awaited()

    def test_concurrent_webhook_and_browser_claim_once(self):
        async def exercise():
            both = asyncio.Event(); lookups = 0
            async def get(*args):
                nonlocal lookups
                lookups += 1
                if lookups == 2: both.set()
                await both.wait()
                return copy.deepcopy(COMPLETED)
            self.get.side_effect = get
            return await asyncio.gather(self.request("POST", "/api/webhooks/paypal", json=CAPTURE_EVENT), self.request("GET", f"/api/checkout/return?order_id=1&token={PPID}"))
        responses = asyncio.run(exercise()); self.assertEqual(responses[0].status_code, 200)
        self.fulfil.assert_awaited_once(); self.mail.assert_awaited_once(); self.metrics.assert_called_once()

    def test_paid_failed_and_shipped_orders_never_reprocessed(self):
        for state in ("paid", "failed", "shipped", "delivered"):
            self.order.status = state; self.db.commit(); self.complete()
        self.get.assert_not_awaited(); self.fulfil.assert_not_awaited()

    def test_supplier_error_preserves_paid_status_without_automatic_repost(self):
        self.fulfil.side_effect = TimeoutError("secret supplier payload")
        self.assertEqual(self.complete(), "paid_cj_pending"); self.assertEqual(self.complete(), "already_paid")
        self.db.refresh(self.order); self.assertEqual(self.order.status, "paid")
        self.assertNotIn("secret", self.order.notes); self.fulfil.assert_awaited_once()

    def test_digital_order_uses_fulfilment_without_duplicate_physical_receipt(self):
        self.product.supplier = "digital"; self.db.commit()
        self.assertEqual(self.complete(), "success"); self.mail.assert_not_awaited(); self.fulfil.assert_awaited_once()

    def test_fallback_and_dry_run_share_guard_without_new_scheduler(self):
        report = asyncio.run(recovery.recover_pending(self.db, main._complete_paypal_order, dry_run=True))
        self.assertEqual(report["candidates"], 1); self.get.assert_not_awaited()
        report = asyncio.run(recovery.recover_pending(self.db, main._complete_paypal_order))
        self.assertEqual(report["recovered"], 1); self.fulfil.assert_awaited_once()
        asyncio.run(recovery.recover_pending(self.db, main._complete_paypal_order)); self.fulfil.assert_awaited_once()

    def test_browser_token_mismatch_never_fetches_or_captures(self):
        response = asyncio.run(self.request("GET", "/api/checkout/return?order_id=1&token=WRONG"))
        self.assertIn("payment_error", response.headers["location"]); self.get.assert_not_awaited()


class PayPalTransport(unittest.TestCase):
    def test_missing_signature_headers_never_call_paypal(self):
        with patch.object(paypal, "PAYPAL_WEBHOOK_ID", "STORE-HOOK"), patch.object(paypal, "_get_access_token", AsyncMock()) as token:
            self.assertFalse(asyncio.run(paypal.verify_webhook({}, APPROVAL_EVENT))); token.assert_not_awaited()

    def test_verification_uses_own_webhook_id_and_full_event(self):
        headers = {"paypal-" + key: "test" for key in ("auth-algo", "cert-url", "transmission-id", "transmission-sig", "transmission-time")}
        requests = []
        async def send(request):
            requests.append(request)
            return httpx.Response(200, json={"verification_status": "SUCCESS"})
        client = httpx.AsyncClient(transport=httpx.MockTransport(send))
        with patch.object(paypal, "PAYPAL_WEBHOOK_ID", "STORE-HOOK"), patch.object(paypal, "_get_access_token", AsyncMock(return_value="unit-token")), patch.object(paypal.httpx, "AsyncClient", return_value=client):
            self.assertTrue(asyncio.run(paypal.verify_webhook(headers, APPROVAL_EVENT)))
        data = json.loads(requests[0].content); self.assertEqual(data["webhook_id"], "STORE-HOOK"); self.assertEqual(data["webhook_event"], APPROVAL_EVENT)

    def test_capture_request_id_is_stable_and_distinct_per_order(self):
        requests = []
        async def send(request):
            requests.append(request); return httpx.Response(200, json=COMPLETED)
        factory = httpx.AsyncClient
        with patch.object(paypal, "_get_access_token", AsyncMock(return_value="unit-token")), patch.object(paypal.httpx, "AsyncClient", side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(send))):
            for ppid in (PPID, PPID, "OTHER1234567890123"):
                asyncio.run(paypal.capture_order(ppid))
        ids = [r.headers["PayPal-Request-Id"] for r in requests]
        self.assertEqual(ids[0], ids[1]); self.assertNotEqual(ids[0], ids[2]); self.assertLessEqual(len(ids[0]), 38)


if __name__ == "__main__":
    unittest.main()
