# Qikink LIVE: authentication only

`services.qikink_live.LiveClient` is separate from the Sandbox client.
It reads QIKINK_LIVE_CLIENT_ID and QIKINK_LIVE_CLIENT_SECRET through
`LiveClient.from_env()`. It authenticates against
https://api.qikink.com/api/token using ClientId and client_secret.

Successful responses require a matching ClientId, a nonempty Accesstoken,
and a positive expires_in. Tokens are not returned in diagnostic reports.

## Production configuration

Credentials stay outside Git in /etc/tbw-qikink-live.env,
owned by root with mode 0600. Never commit this file.
Regenerated secrets must also be updated in the Codex credential vault.

The systemd drop-in provided under deploy/systemd must be installed as:
/etc/systemd/system/thebookswanderer.service.d/70-qikink-live.conf

This is an explicit operational step, not performed by importing this
module. Provision the credential file before installing the drop-in.
Run systemctl daemon-reload and restart the service during a suitable
window. Verify service health afterward.

To undo the environment binding, remove only that drop-in, reload
systemd, and restart the service. Keep the credential file private.

## Restrictions

Both order creation methods always raise before any network request.
No checkout hooks, order submission, wallet operations, automatic
fulfillment, or tracking integration are introduced.
Sandbox behavior and its journal remain unchanged.
Loading credentials does not activate production order fulfillment.

Catalog mapping, final artwork/mockups, destination coverage, verified
supplier costs, and a separately authorized real-order test remain pending.

## Validation

Run server/tests/test_qikink_live.py using the server virtualenv.
Tests use mock HTTP transports and make no real API calls.

During manual VPS validation on 2026-10-20, LIVE authentication succeeded,
variables were present in the service process, and store health was HTTP 200.
No real orders were created.
