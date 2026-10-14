# Product identifiers for Google

The Search Console export of 14 October 2026 names five URLs for three
products. Two URLs are the English and Spanish editions of Readers 2027,
two are Reading Log Bookmarks, and one is Baker Street Book Nook Kit.

The product and variant records now store verified manufacturer metadata.
Product `brand`, `mpn`, and `gtin` fields default to empty; variants may carry
their own `mpn` and `gtin`. Supplier SKUs and provider product ids are not
automatically treated as manufacturer identifiers.

JSON-LD and the Google XML feed share one resolver. It checks GTIN length and
check digit, keeps leading zeroes, and omits malformed GTINs. Product-level
GTINs/MPNs are not copied across products with multiple variants; selected
variants and their feed items use their own identifiers. Brand names are
preserved across translations. The storefront shows known brand/MPN data.

## Readers 2027: the shop's own design

`scripts/import_printify_products.py` lists this calendar in the owner's
Printify shop as product `6acaf5de8ed76a615a0adea3`. The original cover and
monthly artwork are in `assets/products/printify/readers-2027-*.jpg`.

For this exact product, the catalogue declares the brand **The Books Wanderer**
and assigns its own manufacturer reference **TBW-READERS-2027**. No GTIN is
assigned. Google allows the store name and an owner-assigned MPN for private
label/custom products: <https://support.google.com/merchants/answer/6324351>.

The SQLite startup migration adds the missing columns and fills only blank
brand/MPN fields on a record matching the exact slug, supplier and Printify id.
It preserves owner overrides and never labels an arbitrary Printify or CJ item
with the shop's brand. The calendar importer preserves these fields on reimport.

## CJ evidence lookup

Configure `CJ_API_KEY` in the execution environment and allow HTTPS access to
`developers.cjdropshipping.com`, then run:

```bash
server/.venv/bin/python server/scripts/audit_cj_identifiers.py
```

This uses the normal CJ client to query the exact supplier variants
`CJYD207807803CX` (Reading Log Bookmarks) and `CJYZ30260030001` (Baker Street).
It reports relevant identifier/property fields and whether the variant matched.
It does not import products, edit the catalogue, order goods or print credentials.
Generic labels, inventory codes and model names require verification and must
not be automatically published as brands, GTINs or MPNs.

Until CJ supplies reliable evidence, those three reported URLs may retain
their missing-identifier recommendation. `identifier_exists` in the XML feed
is `yes` for a valid GTIN or a verified brand/MPN pair; otherwise its previous
`no` behavior remains. That feed attribute does not silence Search Console's
JSON-LD recommendation.

## Validation and deployment

Offline tests cover feed/PDP/API consistency, Spanish pages, variant isolation,
invalid GTINs, legacy SQLite migration and idempotent/preserved backfill.
Both deployment scripts include the new identifier resolver. The product script
version is bumped so browsers fetch the updated visible metadata.

After deployment, check both calendar URLs and the feed, then run Google's
Rich Results Test and Search Console validation. A local test pass does not
establish Google's acceptance or remove a historic crawl report immediately.
