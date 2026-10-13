# Product structured data: policy review and regression checks

Product pages publish one JSON-LD `Product` plus breadcrumbs. The visible HTML
is not a second microdata Product/Offer. Each active priced variant has an
individual `Offer` with its exact USD price, SKU and `?variant=<id>` URL; a
selected variant page publishes only that variant's offer and displays its
price and image. Different prices are not modeled as an `AggregateOffer`.

## Published policy versus markup

The source of truth is `shipping-returns.html`, with operational context in
`docs/RETURNS_OPERATIONS.md`. This change does not change either policy.

| Topic | Published behavior | Structured data |
| --- | --- | --- |
| Change of mind | Contact us within 14 days of delivery | Finite 14-day return window, policy link |
| Physical return | Usually unnecessary; customer pays postage if requested | No `returnMethod` or `returnFees`: `KeepProduct` is not a valid return method, and unconditional `FreeReturn` is inaccurate |
| Faulty/damaged goods | Replacement or full refund within 30 days, without sending goods back | Remains in the visible policy; does not replace the 14-day change-of-mind window |
| Shipping cost | Included in product prices | Zero USD for each supported country when free shipping applies |
| Charged-shipping override | CJ/Printify quote destination and variant live | Omit unverified rates instead of publishing invented ceilings; the XML feed also stops advertising zero rates |
| Delivery timing | Transit guide only; no fixed packing turnaround | No invented 1–3-day handling time or universal delivery window |
| Supplier restrictions | Printify/CJ-US: US only; Lulu: configured markets | Restrict shipping and return-policy countries accordingly; Lulu's shipping stays included regardless of the CJ/Printify flag |
| Digital downloads | No physical delivery; no separate published no-refund policy | Omit physical shipping and the previously invented no-refund policy |
| Identifiers/reputation | Catalog has supplier SKUs, no verified manufacturer brand/MPN/GTIN or reviews | Keep internal SKUs; omit unsupported brand/MPN/GTIN, reviews and ratings. The XML feed also omits its assumed brand |

Optional Google recommendations may remain for omitted methods, fees, delivery
times, brand/identifiers or reviews. Add them only when backed by verified
catalog data or an actual published policy. Do not change the policy just to
silence a recommendation.

## Validation

From the repository root:

```bash
server/.venv/bin/python -m unittest discover -s server/tests -v
git diff --check
```

The 22 offline regression tests cover JSON-LD extraction from rendered HTML,
absence of duplicate microdata, exact variant prices/URLs/images, equal-price
variants, supplier-specific shipping, paid-shipping overrides, returns,
digital products, Spanish pages, JSON-LD escaping, storefront/catalog routes,
cart totals/validation, legacy redirects and feed-to-landing-page price parity.
They use an isolated in-memory SQLite database and dependency overrides; they
do not import products into the real catalog, charge payments, fulfill orders
or contact supplier APIs. Fixtures are test data, not production product data.

After a separately approved deployment, check representative live physical
and variant pages in Google's Rich Results Test and URL Inspection, then ask
Search Console to validate the reported fixes. Local tests cannot establish
Google indexing or live Merchant Center/Search Console approval. Digital
downloads remain excluded from the physical-product XML feed. No deployment
or merge is part of this change.
