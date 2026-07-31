# CJ Dropshipping API (local reference)

Offline-friendly notes for **CJ API 2.0** as used by The Books Wanderer.  
Official docs (online): https://developers.cjdropshipping.com/

| | |
|---|---|
| **Base URL** | `https://developers.cjdropshipping.com/api2.0/v1` |
| **Auth header** | `CJ-Access-Token: <accessToken>` |
| **API key** | My CJ → Authorization → API → `CJ_API_KEY` in `.env` |
| **Our client** | [`server/services/cj.py`](../../services/cj.py) |

**Never commit real API keys.** Copy `server/.env.example` → `server/.env` on each machine.

---

## Quick setup (new PC after clone)

```powershell
cd C:\repos\thebookswanderer.com\server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env → set CJ_API_KEY (and PayPal if testing checkout)
```

Smoke-test product query:

```powershell
python scripts/fetch_spu.py CJJT1393689
# or
python -c "import asyncio; from services import cj; print(asyncio.run(cj.get_product_details(product_sku='CJJT1393689')).get('productNameEn'))"
```

---

## Auth

| Method | Path | Body |
|--------|------|------|
| POST | `/authentication/getAccessToken` | `{ "apiKey": "..." }` |
| POST | `/authentication/refreshAccessToken` | `{ "refreshToken": "..." }` |

Response `data`:

- `accessToken` — send as `CJ-Access-Token` (~15 days; we cache ~12h)
- `refreshToken` — optional refresh

Client: `cj.get_access_token()`, auto-retry on 401/403.

**QPS:** CJ rate-limits (~1 req/s on some endpoints). Space freight / import calls.

---

## Endpoints we use

See [endpoints.md](./endpoints.md) for params and field notes.

| Use case | Method | Path | Client helper |
|----------|--------|------|----------------|
| Product by SPU/pid/variant | GET | `/product/query` | `get_product_details` |
| Search / list | GET | `/product/listV2` | `search_products` |
| Product videos | POST | `/product/queryVideosByProductId` | `query_videos_by_product_id` |
| Shipping rates | POST | `/logistic/freightCalculate` | `freight_calculate` |
| Place order | POST | `/shopping/order/createOrderV2` | `create_order` |

Optional / scripts:

| Use case | Method | Path | Client helper |
|----------|--------|------|----------------|
| Categories | GET | `/product/getCategory` | `get_categories` |
| Legacy list | GET | `/product/list` | `list_products` |

---

## IDs (important)

| ID | Meaning |
|----|---------|
| **pid** | Product (SPU-level) id |
| **productSku / SPU** | e.g. `CJYD2076904` — human listing code |
| **vid** | Variant id — **required for freight + createOrder** |
| **variantSku** | e.g. `CJYD207690401AZ` |
| **videoNumber** | e.g. `SPCJJT13936890002` (storefront id) |
| **videoId** | Hash id for download URL |

---

## Videos

1. `GET /product/query?productSku=…&features=enable_video` → `productVideo` list of ids  
2. `POST /product/queryVideosByProductId` `{ "productId": "<pid>" }` → `videoUrl`, `videoNumber`, `coverURL`  
3. Download with header: `Referer: https://developers.cjdropshipping.com/`  
4. Prefer **self-hosting** under `assets/products/…` (CJ may rate-limit hotlinks)

---

## Orders after PayPal

Store uses `createOrderV2` with:

- `payType`: env `CJ_PAY_TYPE` — **3** = create only (no wallet charge), **2** = pay from balance  
- Products: `[{ "vid", "quantity" }]`  
- Shipping address from checkout form  

See `server/main.py` → `_submit_to_cj`.

---

## Local vs production

| | Local | VPS |
|---|--------|-----|
| `.env` | Your machine (not in git) | `/var/www/thebookswanderer.com/server/.env` |
| DB | `server/data/store.db` (gitignored) | same path on server |
| Catalog | Import scripts or copy DB | Live imports |

The **client library and this docs folder** are in git. Secrets and SQLite are not.

---

## Related scripts

| Script | Purpose |
|--------|---------|
| `scripts/fetch_spu.py` | Dump SPU JSON to `data/` |
| `scripts/fetch_cj_product.py` | Product fetch helper |
| `scripts/import_*.py` | Curated product imports |
| `scripts/reprice_catalog.py` | Recompute retail from cost bands |
| `scripts/set_product_categories.py` | Assign category slugs |

---

## Official doc map

| Topic | URL |
|-------|-----|
| Docs home | https://developers.cjdropshipping.com/ |
| Auth | https://developers.cjdropshipping.com/en/api/api2/api/auth.html |
| Product | https://developers.cjdropshipping.com/en/api/api2/api/product.html |
| Logistics | https://developers.cjdropshipping.com/en/api/api2/api/logistic.html |
| Shopping / orders | https://developers.cjdropshipping.com/en/api/api2/api/shopping.html |
| Error codes | https://developers.cjdropshipping.com/en/api/api2/standard/ps-code.html |
