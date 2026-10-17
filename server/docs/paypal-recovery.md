# PayPal completion without a browser return

The shop previously completed captures only at `/api/checkout/return`.
The configured webhook ID belonged to MathRelaxing's endpoint. Keep that
subscription intact: the stores share the merchant app.

The Books Wanderer needs its own live subscription at
`https://thebookswanderer.com/api/webhooks/paypal` for:

- `CHECKOUT.ORDER.APPROVED`
- `PAYMENT.CAPTURE.COMPLETED`

Set this subscription's ID as `PAYPAL_WEBHOOK_ID` in this site's private
`server/.env`, preserve the other bindings and file permissions, then restart
`thebookswanderer.service`. Never reuse MathRelaxing's webhook ID. Before
changing configuration, privately back up the environment and SQLite database.
No new PayPal app, SSH account, daemon or cron is required.

## Processing

All signed events are verified through PayPal's verify-webhook-signature API.
Foreign store IDs and unsupported events are acknowledged without processing.
Only a unique, stored `orders.paypal_order_id` can identify a local order.
The canonical order is fetched with this merchant's credentials and checked
for CAPTURE intent, the shop reference, one purchase unit, and exact USD total
before any capture. Only APPROVED orders are captured. Goods are released only
after a canonical COMPLETED order with one matching COMPLETED capture.

The browser, webhook and recovery worker use the same deterministic
`PayPal-Request-Id` for each PayPal order. After transport errors, query PayPal
rather than assume capture failed. An atomic `awaiting_payment -> paid` claim
allows just one caller to send receipts, record a purchase and fulfil the cart.
Webhooks and cron do not use PayPal's delivery IP as the buyer's Meta CAPI IP.
Provider/verification outages return HTTP 503 so PayPal can retry delivery.
Pending payments remain unpaid until a later completed event or recovery pass.

The existing `tbw-order-tracking` cron (every two hours) also checks awaiting
payments created in the last 30 days. This recovers missed notifications without
adding a second scheduler. `sync_order_tracking.py --dry-run` only counts local
payment candidates; it never captures, writes, sends mail or submits suppliers.
The shipping part of that dry run retains its existing read-only provider checks.

## Deliberate limits and operations

Already-paid orders are never automatically resubmitted to CJ, Printify or Lulu
by payment recovery. A supplier timeout, partial fulfilment, or a process crash
after the paid claim needs operator review; blindly retrying could create a
second supplier order. Inspect the existing supplier references before taking
action. Lulu's durable submission guard and read-only reconciliation remain in
place. Its UNPAID jobs still require manual payment in the Lulu portal.

An invalid amount, foreign reference, refunded or incomplete capture must never
release goods. These are logged without buyer payloads. Recovery logs aggregate
counts and exception types; signed event bodies and credentials are not logged.
Before retrying an old checkout manually, inspect canonical PayPal status; the
30-day worker lookback deliberately excludes older historical checkouts.

Verification uses offline mocked payment/supplier/email/analytics calls. Live
checks should inspect registered subscriptions, service health and unsigned
endpoint rejection, without creating orders or sending simulated signed events
to the production fulfilment path.

References:
- https://developer.paypal.com/api/rest/webhooks/rest/
- https://developer.paypal.com/payment-methods/webhooks/
- https://developer.paypal.com/api/rest/reference/idempotency/
