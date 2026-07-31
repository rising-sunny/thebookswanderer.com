# Deploy — thebookswanderer.com

Same VPS pattern as **mathrelaxing.store** (Hetzner + nginx + Certbot + systemd).

| | |
|---|---|
| **VPS IP** | `5.78.125.169` |
| **Path** | `/var/www/thebookswanderer.com/` |
| **Front** | Static HTML/CSS/JS |
| **API** | FastAPI + uvicorn `127.0.0.1:8010` (`thebookswanderer.service`) |
| **nginx** | `/etc/nginx/sites-enabled/thebookswanderer.com` → `/api/*` proxied |
| **DB** | SQLite `server/data/store.db` |
| **Payments** | PayPal (Orders v2 CAPTURE), same env pattern as MathRelaxing |
| **Fulfillment** | CJ Dropshipping API after PayPal capture |

---

## Deploy

```powershell
cd C:\repos\thebookswanderer.com
.\deploy\deploy.ps1
```

Creates `server/.env` on first run (copies `PAYPAL_*` from MathRelaxing if present).  
Set **`CJ_API_KEY`** on the server if empty:

```bash
ssh root@5.78.125.169
nano /var/www/thebookswanderer.com/server/.env
systemctl restart thebookswanderer
```

Health: https://thebookswanderer.com/api/health

---

## Add a product (when you pick one from CJ)

```bash
curl -sS -X POST https://thebookswanderer.com/api/admin/products \
  -H 'Content-Type: application/json' \
  -d '{
    "admin_key": "<SECRET_KEY from .env>",
    "cj_pid": "<CJ product id>",
    "cj_vid": "<optional variant id>",
    "category": "Kindle sleeves",
    "price_usd": 24.99
  }'
```

Do **not** bulk-import; only products you choose.

---

## Checkout flow

1. `POST /api/shipping/quote` — freight by country (CJ) + retail markup  
2. `POST /api/checkout` — creates local order + PayPal checkout URL  
3. Customer pays on PayPal  
4. `GET /api/checkout/return` — capture PayPal → `createOrderV2` on CJ  

`CJ_PAY_TYPE=3` = create order only (no CJ balance charge).  
`CJ_PAY_TYPE=2` = pay from CJ wallet when ready for auto-fulfill.

---

## Logs

```bash
journalctl -u thebookswanderer -n 80 --no-pager
```

---

## CJ Dropshipping API (local clone)

Client + offline cheatsheet ship with the repo (no network required to read):

| | |
|---|---|
| **Client** | `server/services/cj.py` |
| **Docs** | `server/docs/cj-api/README.md` |
| **Endpoints** | `server/docs/cj-api/endpoints.md` |
| **Smoke test** | `cd server && .venv/…/python scripts/cj_api_smoke.py <SPU>` |

Official online docs: https://developers.cjdropshipping.com/

On a new PC: clone → `pip install -r server/requirements.txt` → copy `server/.env.example` to `server/.env` → set `CJ_API_KEY`.