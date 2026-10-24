# Restricted VPS administrative API

Separate FastAPI service for authenticated store reads and read-only CJ
catalog search. This service is not imported by the storefront.

Routes: GET /health, GET /products, GET /suppliers/cj/search,
GET /suppliers/cj/products/{pid}.
All implemented routes require Authorization: Bearer with a dedicated key.
OpenAPI and interactive documentation are disabled.

Store products are queried using SQLite mode=ro. CJ results add the
storefront's suggested retail price (its public pricing preview on
127.0.0.1:8010) and whether the product is already in the store.

The key stays on the VPS. Systemd LoadCredential should deliver admin_key
through CREDENTIALS_DIRECTORY. TBW_ADMIN_KEY_FILE supports local testing.
Only the CJ key is delivered, as cj_api_key, and never returned. The
installer copies it from the store .env into a root-only credential file.

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
up the code and unit, adds the CJ credential, restarts only this service and
restores the backup if the health check fails.

After a rolled-back installation, --resume may reuse the retained key and identical application code. It refuses existing service or Nginx configuration and checks key ownership and permissions. HTTPS readiness is retried for a bounded period after the Nginx reload.
