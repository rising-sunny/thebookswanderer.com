# Pinterest — The Books Wanderer

Publish product pins via **Pinterest API v5**.

| | |
|---|---|
| **Service** | [`server/services/pinterest.py`](../services/pinterest.py) |
| **HTTP routes** | [`server/routers/pinterest.py`](../routers/pinterest.py) |
| **CLI** | [`server/scripts/pinterest_cli.py`](../scripts/pinterest_cli.py) |
| **Token file** | `server/data/.pinterest_token.json` (or `PINTEREST_TOKEN_FILE`) — **TBW only**, never MathRelaxing’s token |

---

## Recommended: option A (reuse MathRelaxing’s approved app)

A **new** Pinterest app can sit in review for weeks. MathRelaxing already has a working production app. Reuse that app’s **client id + secret**, add TBW’s redirect URI, then OAuth **as the The Books Wanderer Pinterest account**.

```
App (MathRelaxing developer app, already approved)
  + OAuth while logged into The Books Wanderer
  = pins / boards on TBW’s profile
```

### 1. Pinterest Developers (same app as MathRelaxing)

1. Open [developers.pinterest.com](https://developers.pinterest.com/) → the **existing** MathRelaxing app.
2. **Redirect URIs** — keep MathRelaxing’s and **add**:
   ```
   https://thebookswanderer.com/api/pinterest/oauth/callback
   ```
3. Confirm scopes include:  
   `boards:read,boards:write,pins:read,pins:write,user_accounts:read,user_accounts:write`
4. Copy **App ID** / **App secret** into TBW `.env` (same values as MathRelaxing’s `PINTEREST_CLIENT_ID` / `PINTEREST_CLIENT_SECRET`).

Do **not** copy MathRelaxing’s `PINTEREST_TOKEN_FILE` / `.pinterest_token.json`. TBW must get its own token via OAuth below.

### 2. Env on TBW (`server/.env` and VPS)

```env
PINTEREST_CLIENT_ID=<same as mathrelaxing>
PINTEREST_CLIENT_SECRET=<same as mathrelaxing>
PINTEREST_REDIRECT_URI=https://thebookswanderer.com/api/pinterest/oauth/callback
PINTEREST_SCOPES=boards:read,boards:write,pins:read,pins:write,user_accounts:read,user_accounts:write
PINTEREST_API_BASE=https://api.pinterest.com/v5
# Token path defaults to server/data/.pinterest_token.json
```

```bash
# on VPS after editing .env
systemctl restart thebookswanderer
```

`SECRET_KEY` (existing admin key) protects OAuth start / status / pin endpoints.

### 3. Connect The Books Wanderer account (OAuth)

1. Browser **private window** (or log out of MathRelaxing on Pinterest).
2. Log in as **The Books Wanderer**.
3. Open:

   ```
   https://thebookswanderer.com/api/pinterest/oauth/start?admin_key=YOUR_SECRET_KEY
   ```

4. Approve permissions → “Pinterest connected”.
5. Check account:

   ```powershell
   cd server
   python scripts/pinterest_cli.py whoami
   ```

   Username / business name should be **TBW**, not MathRelaxing.

---

## Option B (later): dedicated TBW app

When you want a separate app and can wait for review:

1. Create app at [developers.pinterest.com](https://developers.pinterest.com/).
2. Redirect: `https://thebookswanderer.com/api/pinterest/oauth/callback`
3. Replace `PINTEREST_CLIENT_ID` / `SECRET` in `.env`, restart, re-run OAuth.

Same code paths; only credentials change.

---

## CLI

```powershell
cd server
.\.venv\Scripts\Activate.ps1

python scripts/pinterest_cli.py whoami
python scripts/pinterest_cli.py boards
python scripts/pinterest_cli.py create-board "Book accessories" --description "Page holders, bookmarks, clips"
python scripts/pinterest_cli.py pin-product hollow-kitten-bookmark --board-id BOARD_ID --dry-run
python scripts/pinterest_cli.py pin-product hollow-kitten-bookmark --board-id BOARD_ID
```

---

## HTTP (admin_key = SECRET_KEY)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/pinterest/oauth/start?admin_key=` | Starts OAuth |
| GET | `/api/pinterest/oauth/callback` | Pinterest redirect (no key) |
| GET | `/api/pinterest/status?admin_key=` | Config + account |
| GET | `/api/pinterest/boards?admin_key=` | List boards |
| POST | `/api/pinterest/boards` | JSON: admin_key, name, description? |
| POST | `/api/pinterest/pins/product` | JSON: admin_key, board_id, slug |

---

## Claim the website (optional)

Pinterest Business → Claimed accounts → Websites → `thebookswanderer.com`  
(meta tag or HTML file). Separate from OAuth; good for domain verification / rich pins.

---

## Auto-pin: daily drip + launch on new product

| Mode | When | Behaviour |
|------|------|-----------|
| **Launch** | `POST /api/admin/products` or `import_cj_product.py` | Pins new product to category board (+ shop board if different) |
| **Drip** | Cron once/day | Pins `PINTEREST_PINS_PER_DAY` (default 1) active products not pinned in `PINTEREST_REPIN_COOLDOWN_DAYS` (default 45) |

Tracking table: `pinterest_pins` (slug, board, pin_id, kind=`launch`|`drip`, status).

### Env

```env
PINTEREST_AUTO_PIN_ENABLED=1
PINTEREST_LAUNCH_PIN_ENABLED=1
PINTEREST_LAUNCH_ALSO_SHOP=1
PINTEREST_PINS_PER_DAY=1
PINTEREST_REPIN_COOLDOWN_DAYS=45
```

### Cron (VPS)

```cron
# 14:00 UTC ≈ mid-morning US / afternoon EU — adjust to taste
0 14 * * * cd /var/www/thebookswanderer.com/server && /var/www/thebookswanderer.com/server/.venv/bin/python scripts/pinterest_auto_pin.py >> /var/log/tbw-pinterest-auto.log 2>&1
```

### Manual

```bash
cd /var/www/thebookswanderer.com/server
.venv/bin/python scripts/pinterest_auto_pin.py --dry-run
.venv/bin/python scripts/pinterest_auto_pin.py
.venv/bin/python scripts/pinterest_auto_pin.py --limit 2
```

Launch pin is best-effort: a Pinterest failure does **not** roll back product import.

---

## Security

- Never commit tokens or client secrets.
- Never reuse MathRelaxing’s **access token** on TBW.
- Prefer private OAuth start URLs (`admin_key` is a secret).
