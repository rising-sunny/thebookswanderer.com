# Product dates and publication receipts

The authenticated connector exposes business metadata, without provider keys
or customer data. Existing OAuth, app identity and write permissions are unchanged.

## What the dates mean

| Source | Meaning | Coverage |
| --- | --- | --- |
| Store `created_at` | When the product row was created, possibly as a hidden draft | Existing rows with a valid date |
| Store `published` / `unpublished` | Visibility changed in a committed ORM transaction | From installation of the receipt table onward |
| Pinterest `pin_recorded` | The store recorded a successful pin | Local receipt time, not first product publication |
| Etsy `original_created_at` | Etsy's original listing creation metadata | Current listing snapshot |
| Etsy `created_or_renewed_at` | Etsy's creation/renewal metadata | Can change with renewal |
| Etsy `state_changed_at` | Etsy's last state-change metadata | Does not identify every earlier publication |

The store ledger is append-only for ORM product inserts, visibility changes,
and live-product deletions. Rollbacks remove the receipt too. Title/slug
snapshots survive product deletion. Existing products are not backfilled.
Direct SQL and ORM bulk updates bypass mapper listeners and are not covered.
The `tracking_started_at` marker is written once when the ledger table is
created; no database or credential is copied out of the VPS.

`GET /products` adds creation dates, platform IDs and the latest recorded
publication per product ID/slug. `published_at` remains null: it is not a
claim about the product's first-ever publication.

`GET /products/activity?day=2026-10-29&timezone=America/Santiago` returns a
bounded, paginated timeline. Optional filters: `platform=store|pinterest|all`
and `product_id`. `start_utc` is inclusive and `end_utc_exclusive` is exclusive.
Always check coverage and `has_more` before concluding there were no events.

`GET /suppliers/etsy/listings?state=active&limit=50&offset=0` uses the existing
authenticated loopback bridge. Only GET calls go to the configured Etsy shop;
the response includes listing IDs, titles, states, canonical URLs and UTC dates.
The other available states are inactive, draft, sold_out and expired.
An unavailable source produces an error, never a false empty result.

## Deploy on the existing VPS installation

The normal storefront deployment must first include this change's `main.py`
and `models.py`. On its startup, `init_db()` creates the additive receipt table;
it does not rewrite or backfill existing products. The CI deployment checks
include the offline publication tests. The admin API and MCP are **separate**
services and are not installed by that storefront deployment.

After the storefront deployment, an authorized VPS operator should use a
checkout containing the same reviewed revision. From its repository root,
run the existing upgrade workflows, not the first-install commands:

```bash
sudo /var/www/thebookswanderer.com/server/.venv/bin/python deploy/admin-api/install.py --upgrade --check
sudo /var/www/thebookswanderer.com/server/.venv/bin/python deploy/admin-api/install.py --upgrade
sudo /opt/tbw-mcp/.venv/bin/python deploy/mcp/install.py --upgrade --check
sudo /opt/tbw-mcp/.venv/bin/python deploy/mcp/install.py --upgrade
```

The installers preserve the existing credentials/OAuth state and back up the
previous service code for rollback. Do not print keys or copy production
databases. If the storefront must be rolled back, the additive receipt table
can stay in place; preserve its records.

Refresh the existing plugin's MCP tool discovery after upgrading; adding a new
plugin is unnecessary. Reauthorize only if the host requests it. Verify:

1. `tbw_health` includes `products:activity` and `etsy:listings:read`.
2. `tbw_list_products` returns `created_at` and platform IDs.
3. `tbw_product_activity` returns the requested Santiago day and coverage.
4. `tbw_list_etsy_listings` returns safe metadata, or a clear connection error.

These four checks are reads; they must not create a product, pin, order or ad.

## Offline checks

Use Python 3.12 and separate virtual environments: the storefront and MCP
have different pinned dependency versions.

```bash
# Storefront/admin virtualenv, no production .env or database:
python -m unittest discover -s server/tests -v
python -m unittest discover -s deploy/admin-api -v

# MCP virtualenv installed from deploy/mcp/requirements.lock:
python -m unittest discover -s deploy/mcp -v
```
