# Homepage design preview

Unlinked, noindex/nofollow visual proposal for The Books Wanderer, prepared
for owner review. It is separate from the production homepage template.

- `index.html`: English. `es.html`: Spanish.
- Six selected active products with current API price snapshots, linking to
  their real product pages; category, policy and reading-guide links are live.
- Real cover previews from the already-published nature editions. Historical
  art provenance remains with the original product pages and source records.
- Local Playfair Display and Karla font files; SIL OFL notices included.
- No analytics, signup submissions, checkout forms, product activation or API
  writes in this preview. Links carry `tbw_test=1` to exclude review visits.
- Mobile navigation supports aria-expanded and Escape; reduced-motion preference
  is respected. Images are dimensioned and lower sections are lazy loaded.

Visual and browser checks completed at 390 and 1440 px in both languages:
no horizontal overflow, all images render, six linked cards, working mobile
navigation, no browser script errors. The English first product appears around
980 px on mobile, versus the current general catalogue section around 4656 px.

Product prices are a preview snapshot; preserve dynamic supplier/product data,
localization and the current purchase flow when applying the design to production.
