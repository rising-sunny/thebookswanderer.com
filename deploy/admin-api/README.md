# Restricted VPS administrative API

Separate FastAPI service for authenticated product reads and isolated
Qikink draft preparation. This service is not imported by the storefront.

Routes: GET /health, GET /products, GET /drafts,
GET /drafts/{reference}, POST /drafts.
All implemented routes require Authorization: Bearer with a dedicated key.
OpenAPI and interactive documentation are disabled.

Store products are queried using SQLite mode=ro. Drafts use a separate
SQLite journal with atomic reference reservation. Identical retries return
the same draft; changed content under an existing reference returns 409.
Drafts are not store products and cannot be purchased.

The key stays on the VPS. Systemd LoadCredential should deliver admin_key
through CREDENTIALS_DIRECTORY. TBW_ADMIN_KEY_FILE supports local testing.
Provider credentials are neither loaded nor exposed by this service.

Production paths:
- Key: /etc/tbw-admin-api/key, root-owned, mode 0600.
- Drafts: /var/lib/tbw-admin-api/drafts.sqlite3.
- Store: /var/www/thebookswanderer.com/server/data/store.db, read-only.
- Planned HTTPS prefix: /api/ops/, proxying to loopback only.

Installation, systemd sandboxing, Nginx configuration and authenticated
HTTPS verification are pending. This PR alone does not install the service.

No supplier API requests, wallet operations, checkout hooks, publication,
real order creation, or social posting are implemented.
Supplier SKU, artwork, costs, shipping and prices still need verification.

Run test_admin_api.py with the shop virtualenv; tests use temporary databases,
a fake key and TestClient. They make no external API calls.
Operational access from a chat still requires an authenticated HTTP tool
or a working executor; deploying this service does not repair Codex.

## Installer

Run install.py --check as root using the shop virtualenv before installation.
Run install.py without arguments to supply a new dedicated administrative key.
The installer tests local and public HTTPS authentication, product reads, draft storage access, and storefront health. It creates no draft or order.
It uses systemd LoadCredential and a restricted service on 127.0.0.1:8878.
Failures trigger removal of the new Nginx inclusion and service configuration; credentials, state and backups are retained for diagnosis.
Do not rerun over an existing installation or rotate its key implicitly.
