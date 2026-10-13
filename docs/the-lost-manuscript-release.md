# The Lost Manuscript — English physical edition

- Listing: `/products/the-lost-manuscript` (Spanish storefront: `/es/products/the-lost-manuscript`). The book itself is in English.
- Six connected cases, 24 puzzles, 96 interior pages; 6 × 9 inch paperback, grayscale interior, colour matte cover.
- Price: USD 27.99. Shipping included to Lulu destinations configured by the store. Delivery estimate follows the existing Lulu integration.
- Original publisher logo on the title/imprint pages and both cover panels. Cover dimensions obtained from Lulu: 902 × 666 pt, including bleed and a 20 pt spine. No fabricated ISBN, GTIN, reviews or ratings.
- Public sample and product images show actual pages without solutions. The complete print PDFs are private.

## Publication

`server/scripts/lost_manuscript_product.json` contains the listing and print-file checksums. `publish_lost_manuscript.py` updates only this product. It does not run the bulk catalogue importer or publish social posts.

The PDFs travel as an OpenSSL CMS encrypted bundle, using a transport certificate whose private key remains in the server's private digital directory. The transport helper never activates a product. The publisher verifies checksums, installs versioned files outside the public web root and submits them to Lulu's file-validation endpoints. It requires **NORMALIZED** for both interior and cover before activating the English variant.

The file validation does not create a print job or charge the Lulu account. Customers' paid orders use the existing Lulu fulfillment path.

```bash
python scripts/publish_lost_manuscript.py          # listing dry run
python scripts/publish_lost_manuscript.py --apply  # private install, validation, activation
```

The server records successful validation in its private `.release-private/lost-manuscript-published.json`. Signed print-file URLs and private keys must not be copied into repository files or Action logs.

## Checks

The final manuscript was checked for unique puzzle solutions, page references, preserved first-case clues, text margins, embedded fonts, grayscale interior images and image resolution of at least 300 dpi. The 22 existing storefront/schema regressions passed. A temporary-database integration check covered repeat imports, English/Spanish product pages, the English variant, cart price, free US/GB shipping and rejection of an unsupported destination.

No physical proof copy was ordered during this release.
