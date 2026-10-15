# Sakura A5 fabric cover

Selected CJ product: `155149A4-8ADA-445F-8F26-44C4596CD754`.
Selected variant: `3085EA0A-CC79-4D54-B326-91687DCCA0C7`.
Selected SKU: `CJJJJTJT36003-Navy Blue-A5` (cover only; no notebook).
Retail: USD 19.99, standard US shipping included. Origin: CN.

The owner requested publication without a sample on 2026-10-15. The listing
uses the supplier's A5 designation and explains that fit depends on notebook
cover dimensions and spine thickness. CJ repeats the same variantStandard
fields across A5 and A6 variants, so these fields are not used as measured
usable dimensions or maximum spine thickness. No specific journal compatibility
or future sample inspection is promised.

The original supplier photographs were inspected and retained without edits:

| Local image | Supplier URL |
| --- | --- |
| main.jpg | https://cf.cjdropshipping.com/203106/976218633432.jpg |
| detail.jpg | https://cf.cjdropshipping.com/d68f6da7-5047-4500-b6c3-177adf260b48.jpg |
| inside.jpg | https://cf.cjdropshipping.com/0e6a03a2-3cfd-41fe-a575-625a9ad8836d.jpg |

The red variant, a mixed-size photograph and a duplicate hero are omitted.
No supplier claim of handmade production, fibre composition or Japanese
manufacture has been carried into the listing.

Deploy normally with GitHub Actions, then publish this selected product:

```sh
gh workflow run run-script.yml -f script=prepare_a5_cover.py -f args=--publish
```

The routine rechecks CJ's exact variant/SKU, stock, cost and US freight, then
atomically applies the current listing copy and activates this one product.
Repeating publication preserves product and variant IDs. Supplier/slug collisions
and duplicate supplier listings are rejected. Only the selected A5 cover is
mapped for fulfillment; other supplier variants are not imported. No sample,
customer order, payment, or social launch is initiated by this routine.

`--draft` remains available for inactive preparation and refuses to hide an
already-active product. Without arguments the script only prints a dry run.
The supplier-validation report is stored in private server data and records
whether sales were activated. The old preview URLs are noindex redirects to
the real product pages in Spanish and English.

Validation: exact SKU/variant, idempotent publication from the existing draft,
active-listing protection, supplier mismatch, current cost/freight bounds,
English/Spanish copy, product page, cart, checkout, feed and sitemap.
