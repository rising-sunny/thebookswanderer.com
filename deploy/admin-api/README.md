# Restricted VPS administrative API

Separate FastAPI service for authenticated store reads, read-only CJ
catalog search and hidden CJ drafts. This service is not imported by the storefront.

Routes: GET /health, GET /products, GET /suppliers/cj/search,
GET /suppliers/cj/products/{pid}, POST /drafts/preview, POST /drafts,
POST /drafts/{id}/update, POST /drafts/{id}/publish/preview,
POST /drafts/{id}/publish, POST /drafts/{id}/delete,
POST /products/{id}/unpublish/preview, POST /products/{id}/unpublish.
GET /suppliers/printify/products, GET /suppliers/printify/products/{id},
GET /suppliers/prodigi/products/{sku}, GET /products/{id}/shipping
(read through the storefront, which keeps the Printify/Prodigi/Lulu keys),
and POST /suppliers/{cj|printify|lulu|prodigi}/api: any call to that API,
made by the storefront with its key. Writes need a single-use code from
?preview=true (bound to the exact request, valid 10-20 minutes); paths for
orders and payments are refused unless TBW_SUPPLIER_ORDERS_ENABLED=1 is set
in the store's .env. Customer personal data is redacted from responses and
each call is logged (supplier, method, path) in the store's journal.
All implemented routes require Authorization: Bearer with a dedicated key.
OpenAPI and interactive documentation are disabled.

Store products are queried using SQLite mode=ro. CJ results add the
storefront's suggested retail price (its public pricing preview on
127.0.0.1:8010) and whether the product is already in the store.

The key stays on the VPS. Systemd LoadCredential should deliver admin_key
through CREDENTIALS_DIRECTORY. TBW_ADMIN_KEY_FILE supports local testing.
Only the CJ key is delivered, as cj_api_key, and never returned. The
installer copies it from the store .env into a root-only credential file.

Drafts are built by the storefront's loopback-only POST /api/internal/drafts
(inactive, draft=1, no Pinterest pin), which also edits drafts and publishes
them. Publishing needs a code from the preview, an HMAC of the draft's
current state, and a ready draft (description, store category, image, price
above cost). Only rows with draft=1 and active=0 are edited, published or deleted
(deletion also requires no orders); unpublishing turns a live product back
into a draft, with its own preview code. Publishing pins on Pinterest only
when pin=true. This service
still never writes store.db. Both sides use draft_key, /etc/thebookswanderer/draft_key
(root:www-data, 0640), which --upgrade generates if missing. The store reads
it on each request, so it needs no restart.

Production paths:
- Key: /etc/tbw-admin-api/key, root-owned, mode 0600.
- CJ key: /etc/tbw-admin-api/cj_api_key, root-owned, mode 0600.
- Store: /var/www/thebookswanderer.com/server/data/store.db, read-only.
- Planned HTTPS prefix: /api/ops/, proxying to loopback only.

Installation, systemd sandboxing, Nginx configuration and authenticated
HTTPS verification are pending. This PR alone does not install the service.

Supplier requests are read-only CJ product queries. No wallet operations,
checkout hooks, publication, real order creation, or social posting exist.

Run test_admin_api.py with the shop virtualenv; tests use temporary databases,
a fake key and TestClient. They make no external API calls.
Operational access from a chat still requires an authenticated HTTP tool
or a working executor; deploying this service does not repair Codex.

## Installer

Run install.py --check as root using the shop virtualenv before installation.
Run install.py without arguments to supply a new dedicated administrative key.
The installer tests local and public HTTPS authentication, product reads and storefront health. It creates no product or order.
It uses systemd LoadCredential and a restricted service on 127.0.0.1:8878.
Failures trigger removal of the new Nginx inclusion and service configuration; credentials, state and backups are retained for diagnosis.
Do not rerun over an existing installation or rotate its key implicitly.
On an existing installation use --upgrade (after --upgrade --check): it backs
up the code and unit, adds the CJ and draft credentials, restarts only this
service and restores the backup if the health check fails. It refuses to run
until the deployed store answers its draft route.

After a rolled-back installation, --resume may reuse the retained key and identical application code. It refuses existing service or Nginx configuration and checks key ownership and permissions. HTTPS readiness is retried for a bounded period after the Nginx reload.
