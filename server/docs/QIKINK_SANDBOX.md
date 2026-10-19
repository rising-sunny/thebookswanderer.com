# Qikink Sandbox backend

This client implements India plain-product and fully specified DTG printed
Sandbox test flows. It has no checkout hooks, production host selector, wallet
endpoint, payment capture, artwork upload, or automatic retry of order creation.
Existing store behavior is unchanged. Live fulfillment needs a separate integration.

Reference: https://documenter.getpostman.com/view/26157218/2sBYAysUHS
The supplied PDF documents plain products with print_type_id=1 and no designs.
It also warns that Get Order is unavailable in Sandbox. The observed routes
returned 404 (/api/order/list) and 500 (/api/order).

## Configuration

Use the existing server/.env (never commit credentials):

```dotenv
QIKINK_ENV=sandbox
QIKINK_SANDBOX_CLIENT_ID=...
QIKINK_SANDBOX_CLIENT_SECRET=...
```

QIKINK_ENV defaults to sandbox; any other value is refused. There is no live URL
configuration: calls always use https://sandbox.qikink.com, with redirects off.
The CLI reads server/.env without replacing already exported variables. Run it
as the same Unix user using the same persistent journal each time. On the VPS,
the app service runs as www-data; use that ownership for the journal if running
scripts as root first. No service restart is needed for standalone CLI commands.

## Commands (from server/)

```bash
.venv/bin/python scripts/qikink_sandbox.py auth
.venv/bin/python scripts/qikink_sandbox.py plain --reference tbw_test001
# Above is a dry run, without network calls or order creation.
# Explicit submission, ONLY when a new Sandbox order is wanted:
.venv/bin/python scripts/qikink_sandbox.py plain --reference tbw_test001 --submit-sandbox
.venv/bin/python scripts/qikink_sandbox.py lookup 24616032
.venv/bin/python scripts/qikink_sandbox.py status tbw_test001
```

CLI plain defaults match the successfully tested SKU MVnHs-Wh-S, quantity 1,
value 1, Prepaid, no design, synthetic India address. These are test values, not
pricing or customer data. `lookup` returns exit code 2 for an unverified read;
this never changes a confirmed creation into a failure or creates a replacement.
Exit code 1 indicates a failed command, 0 a completed command or dry run.

### Preserve the already created order (no API call)

The operator confirmed a successful response for reference tbw_9ba7265277,
order ID 24616032. Register that exact plain test payload in the local journal:

```bash
.venv/bin/python scripts/qikink_sandbox.py remember --reference tbw_9ba7265277 --order-id 24616032
.venv/bin/python scripts/qikink_sandbox.py status tbw_9ba7265277
```

`remember` is a local assertion by the operator, not remote verification. It
accepts only this CLI's plain test payload (including --sku if specified), and
refuses to replace a pending/uncertain record or an existing different ID. Do not
use it for a different payload or account. It does not reserve a remote reference.

## Printed Sandbox test (DTG)

```bash
.venv/bin/python scripts/qikink_sandbox.py printed --reference tbw_print001
# Above: dry run, no network. Explicitly submit ONE test when wanted:
.venv/bin/python scripts/qikink_sandbox.py printed --reference tbw_print001 --submit-sandbox
.venv/bin/python scripts/qikink_sandbox.py status tbw_print001
```

Uses the same catalog SKU MVnHs-Wh-S, print_type_id=1 (DTG), quantity/value 1,
Prepaid and the synthetic India address. Adds one front design, 2 x 2 inches,
using https://thebookswanderer.com/assets/logo.png. This existing store logo
is 512 x 512 pixels (256 pixels/inch at 2 inches). The mockup URL deliberately
uses the SAME logo as a Sandbox technical placeholder: it is not a product mockup,
product listing or evidence that Qikink printed anything. No image is published
or changed by this command. SKU/DTG compatibility still needs remote validation.

The design code defaults to the reference plus _d (tbw_print001_d). Keep it
stable for retries of that order; use a new code for different artwork, since
Qikink may reuse an existing design code. No fields are left blank. Supports
--sku, --design-code, --design-url, --mockup-url, --width and --height.

Before authentication or creation, new printed submissions fetch each distinct
image URL WITHOUT Qikink credentials. Only HTTPS store-domain URLs with no query,
fragment, credentials or custom port are accepted. Responses must be HTTP 200,
no redirect, image/png or image/jpeg, at most 4 MiB, and verifiable PNG/JPEG
content up to 40 million pixels. A preflight failure records not_sent, permitting
a retry with the same payload after the hosting problem is fixed. It does not
prove Qikink can fetch the file from its own network.

Widths/heights must be positive and at most 16 x 20 inches (DTG); new design codes
are limited to 20 characters. Printed payloads share the same journal as plain
orders, so a plain reference cannot accidentally be reused for a printed order.

## Duplicate protection and recovery

The independent SQLite file server/data/qikink_sandbox.db stores account hashes,
references, payload hashes, states, IDs and timestamps. No token, secret, address,
email, or request/response body is stored. It does not touch store.db.

Atomic SQLite reservations protect concurrent workers sharing this same file.
Always reuse the same reference for the same logical order and preserve the
journal. A different payload with the same reference is refused. A created record
returns its saved ID without authentication or another POST.

- pending: reservation exists; a crashed process may have submitted the request.
- not_sent: authentication failed before the creation call; same payload can retry.
- rejected: creation returned HTTP 400; no automatic retry for this reference.
- uncertain: timeout, cancellation, redirect, HTTP error other than 400, malformed
  response, missing/invalid ID, or ambiguous result. Submission stays blocked.
- created: HTTP 200 + status_code=200 + a positive numeric order_id was recorded,
  or an operator registered an already confirmed test.

Do not delete the journal, switch --journal paths, generate a new reference, or
clear an uncertain/pending row merely to retry an ambiguous submission. Reconcile
with Qikink/dashboard/support first. The local guard cannot cover orders created
outside it unless registered, or independent machines with different databases.
A database commit failure after remote success can leave pending; keep it blocked.

The access token is cached until expiry within one client instance. Qikink's token
endpoint replaces previous tokens; avoid competing token generators in separate
processes. Authentication problems are surfaced; order POSTs are never replayed.

## Offline verification

```bash
# From repository root; mocked HTTP, temporary SQLite, no remote orders:
server/.venv/bin/python -m unittest discover -s server/tests -p 'test_qikink*.py' -v
```

Live evidence supplied by the operator, not rerun by these tests:
authentication HTTP 200; plain creation HTTP 200, ID 24616032;
lookup /api/order/list HTTP 404 and /api/order HTTP 500. Physical printed fulfillment,
shipping quotes, tracking, payments, and production readiness remain unverified.
The DTG client is covered by offline tests; remote printed creation is not yet confirmed.
