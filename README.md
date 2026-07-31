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

### Deploy

See [`deploy/DEPLOY.md`](deploy/DEPLOY.md). Production VPS runs the same tree under `/var/www/thebookswanderer.com/`.

### Storefront

- Catalog + categories: `index.html`, `app.js`
- PDP: `product.html`, `product.js`
- Cart / checkout: `cart.html`, `checkout.html` (+ `cart.js`, `checkout.js`)
- API: `server/main.py` (products, shipping quote, PayPal, CJ order)
