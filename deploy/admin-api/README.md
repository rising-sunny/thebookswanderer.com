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

After a rolled-back installation, --resume may reuse the retained key and identical application code. It refuses existing service or Nginx configuration and checks key ownership and permissions. HTTPS readiness is retried for a bounded period after the Nginx reload.

## Read-only Qikink catalog snapshot

`GET /qikink/catalog?query=bookmark&limit=5&offset=0` requires the existing admin
bearer credential. Optional `sku` matches the exact, case-sensitive SKU. The
route reads a JSON file; it does not open the store database, create a draft,
request a supplier token, query orders or contact Qikink. All write methods on
this route are absent. Maximum page size is 100.

Configure `TBW_QIKINK_CATALOG_FILE`, default
`/etc/tbw-admin-api/qikink-catalog.json`. An operator must obtain actual data
from Qikink's SKU Descriptions or My Products, normalize it to the following
schema and record the source and retrieval time. There is no automatic import
or live API adapter in this change. Do not put account credentials or customer
information in this file. Example (the SKU below is explicitly fictitious):

```json
{
  "schema_version": 1,
  "source": "Qikink SKU Descriptions — manually exported",
  "retrieved_at": "2026-10-20T00:00:00Z",
  "variants": [
    {
      "product_title": "Bookmark",
      "name": "Classic",
      "qikink_sku": "EXAMPLE-NOT-A-REAL-SKU",
      "sku_kind": "product"
    }
  ]
}
```

`sku_kind=product` identifies a blank-product SKU from SKU Descriptions;
`sku_kind=store` identifies a design-specific SKU from My Products. Keep these
separate; do not infer either code from a product name or the website's ID.
Duplicate SKUs, unknown fields, timezone-less/future retrieval times, over
10,000 variants, files over 5 MB and malformed files are rejected with a safe
503 response. The file is not created by lookup. An intentionally empty, valid
snapshot returns zero variants. Every response includes source_mode,
retrieved_at and live_verified=false, even for an exact match. Verify age,
SKU validity, artwork and shipping before any later use.

Activation after code review (not performed by this change):
1. Deploy the updated admin `app.py` and MCP `tbw_mcp.py` together using the
   existing VPS release process. Do not rerun the initial installers on an
   existing installation; they deliberately refuse it.
2. Install a real, validated snapshot atomically at the configured path, owned
   by root and readable by the existing admin service user (e.g. mode 0640).
   The services must not have write permission to the file or its directory.
3. Restart only the admin and MCP services, keeping existing keys and OAuth
   configuration. Refresh MCP tools in the client to discover the new tool.
4. Verify unauthorized access fails, a known exact SKU matches, a missing SKU
   returns zero, and health still reports publication and order submission false.

A direct Qikink adapter requires separate verified documentation for a catalog
read endpoint and its response schema. Do not guess paths or test SKUs by
creating orders. The Orders 08-25 token endpoint replaces the previous token,
so catalog lookup must not casually reuse order authentication flows either.
