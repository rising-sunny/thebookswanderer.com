# The Books Wanderer

Literary boutique storefront: static front + FastAPI, CJ Dropshipping fulfillment, PayPal checkout.

## Clone on a new machine

```powershell
git clone https://github.com/rising-sunny/thebookswanderer.com.git
cd thebookswanderer.com\server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env: CJ_API_KEY, and optionally PayPal keys for local checkout tests
```

### CJ Dropshipping API (in this repo)

| Path | What |
|------|------|
| [`server/services/cj.py`](server/services/cj.py) | Async API client (auth, product, video, freight, order) |
| [`server/docs/cj-api/README.md`](server/docs/cj-api/README.md) | Setup + how we use CJ |
| [`server/docs/cj-api/endpoints.md`](server/docs/cj-api/endpoints.md) | Endpoint cheatsheet |
| [`server/scripts/cj_api_smoke.py`](server/scripts/cj_api_smoke.py) | Connectivity smoke test |

```powershell
cd server
.\.venv\Scripts\python scripts/cj_api_smoke.py CJYD2076904
```

Official docs (online): https://developers.cjdropshipping.com/

### Facebook Page posts (organic)

Publish product promos from this repo (Graph API — not Ads MCP).

| Path | What |
|------|------|
| [`server/scripts/fb_post.py`](server/scripts/fb_post.py) | text / photo / carousel / video |
| [`server/scripts/post_product_fb.py`](server/scripts/post_product_fb.py) | promo from live catalog slug |
| [`server/docs/FACEBOOK.md`](server/docs/FACEBOOK.md) | setup + commands |

```powershell
cd server
# .env must have FB_PAGE_ID + FB_PAGE_TOKEN
python scripts/fb_post.py whoami
python scripts/post_product_fb.py hollow-kitten-bookmark --dry-run
python scripts/post_product_fb.py hollow-kitten-bookmark
# Video promo (slideshow or product clip)
python scripts/make_slideshow_video.py data/butter_imgs/d6.jpeg data/butter_imgs/d9.jpeg -o ../assets/products/butterfly-bookmark/promo.mp4
python scripts/post_product_fb.py butterfly-metal-bookmark --video ../assets/products/butterfly-bookmark/promo.mp4
```

Meta **Ads** (campaigns) use a separate official MCP: `https://mcp.facebook.com/ads` — see FACEBOOK.md.

### Deploy

See [`deploy/DEPLOY.md`](deploy/DEPLOY.md). Production VPS runs the same tree under `/var/www/thebookswanderer.com/`.

### Storefront

- Catalog + categories: `index.html`, `app.js`
- PDP: pretty URLs `/products/{slug}` (legacy `product.html?slug=` 301s), `product.js`
- Affiliate picks: `/picks/{slug}` (legacy `pick.html?slug=` 301s)
- Sitemap: dynamic `GET /sitemap.xml` from FastAPI (live catalog + lastmod)
- Brand assets: optimized `assets/logo.webp` (CSS), `assets/og-default.jpg` (1200×630 OG/Twitter), favicons
  - Rebuild: `python server/scripts/optimize_brand_assets.py`
- Collections: `/collections` + `/collections/{slug}` (SSR, JSON-LD CollectionPage + ItemList)
- Cart / checkout: `cart.html`, `checkout.html` (+ `cart.js`, `checkout.js`)
- API: `server/main.py` (products, shipping quote, PayPal, CJ order)
