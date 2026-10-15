# Sakura A5 fabric cover: sample-review draft

Selected CJ product: `155149A4-8ADA-445F-8F26-44C4596CD754`.
Selected variant: `3085EA0A-CC79-4D54-B326-91687DCCA0C7`.
Selected SKU: `CJJJJTJT36003-Navy Blue-A5` (cover only; no notebook).
Retail: USD 19.99, standard US shipping included. Origin: CN.

This is an **inactive draft** pending inspection of a physical sample, as
recommended in the selection discussion. Do not infer the usable dimensions
or maximum spine thickness from CJ's variantStandard fields: they repeat the
same dimensions across A5 and A6 variants. Do not promise compatibility with
the Book Club Companion or Reading Passport before testing it.

The original supplier photographs were inspected and retained without edits:

| Local image | Supplier URL |
| --- | --- |
| main.jpg | https://cf.cjdropshipping.com/203106/976218633432.jpg |
| detail.jpg | https://cf.cjdropshipping.com/d68f6da7-5047-4500-b6c3-177adf260b48.jpg |
| inside.jpg | https://cf.cjdropshipping.com/0e6a03a2-3cfd-41fe-a575-625a9ad8836d.jpg |

The red variant, a mixed-size photograph and a duplicate hero are omitted.
No supplier claim of handmade production, fibre composition or Japanese
manufacture has been carried into the listing.

Deploy normally with GitHub Actions. Then prepare the draft:

```sh
gh workflow run run-script.yml -f script=prepare_a5_cover.py -f args=--draft
```

The routine rechecks CJ's exact variant/SKU, stock, cost and US freight before
idempotently storing the inactive listing. It refuses supplier/slug collisions,
duplicate supplier listings and changes to an already-active listing. It does
not activate the product, order a sample, initiate payment, or send a launch.
Only the selected A5 cover is mapped for fulfillment; other supplier variants
are not imported. The supplier-validation report is in private server data.

Preview URLs (noindex, no tracking, sales disabled):
`/assets/products/japanese-a5-book-cover/preview.html` and `preview-en.html`.
The active catalog, sitemap, shopping feed and social jobs skip the draft.

Before activation, inspect one sample for usable size, spine clearance, fabric
finish, colour, flap stitching and care requirements. Replace the pending-fit
copy in the JSON and Spanish overlay with measured facts. Confirm the desired
launch destinations and recheck stock/freight. The existing set_product_active
routine can activate the approved product after the final copy is applied.
