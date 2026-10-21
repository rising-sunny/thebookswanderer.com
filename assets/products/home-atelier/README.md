# Production homepage design

Approved botanical homepage, promoted from `../home-atelier-preview/`.

- `index.html` at the site root is the English source template. Spanish follows
  the existing `server/i18n/es.json` localization and `/es/` routing.
- `server/ssr.py` fills the six-product editorial shelf from active database
  products, including live variant prices, localized titles and current images.
  Retired selections are replaced with other active products. The complete
  catalog remains at `/products/` and `/es/products/`.
- `home.js` handles mobile navigation, the animation pause control, scroll
  reveals and the existing newsletter subscription API. Tracking, cookie choices,
  language preference and cart state still use the shared site scripts.
- Fonts, original botanical linework and real cover crops reuse the neighboring
  preview assets. Playfair Display and Karla retain their bundled OFL notices.
- No database migrations, supplier orders or changes to payment/fulfillment.

Validation: isolated homepage rendering/data tests plus the storefront regression
suite; browser checks in both languages at 320, 390, 768 and 1440 px. Subscription
success/failure is checked with intercepted responses, never a real mailing.

Homepage cover images use responsive WebP exports at 240, 400, 600 and 800 pixels wide, shared by the hero and nature section. The original PNG crops in `../home-atelier-preview/` remain unchanged. Regenerate with `python server/scripts/optimize_home_cover_images.py` (Pillow with WebP support). The `sizes` hints follow the existing CSS cover dimensions and breakpoints; the hero loads eagerly and the nature section stays lazy-loaded.
