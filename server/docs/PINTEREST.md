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

New products are picked up automatically: every run re-queries active products
and sorts **never-pinned first**, so anything you add jumps to the front of the
queue. It only needs an image (own `image_url` or a variant's) — products
without one are skipped silently.

```env
PINTEREST_AUTO_PIN_ENABLED=1
PINTEREST_LAUNCH_PIN_ENABLED=1
PINTEREST_LAUNCH_ALSO_SHOP=1
PINTEREST_PINS_PER_DAY=1
PINTEREST_REPIN_COOLDOWN_DAYS=45
PINTEREST_REAUTH_WARN_DAYS=14
```

### Cron (VPS) — must run as `www-data`

```cron
# 14:00 UTC ≈ mid-morning US / afternoon EU — adjust to taste
0 14 * * * cd /var/www/thebookswanderer.com/server && sudo -u www-data /var/www/thebookswanderer.com/server/.venv/bin/python scripts/pinterest_auto_pin.py >> /var/log/tbw-pinterest-auto.log 2>&1
```

> **Do not drop the `sudo -u www-data`.** The app runs as `www-data`. A refresh
> triggered by a root-owned cron used to replace `.pinterest_token.json` with a
> `root:root 0600` file, after which the app could no longer read its own token
> — `read_token()` swallows the `PermissionError` and every call just looks like
> "not connected". `write_token()` now restores the previous owner as a second
> line of defence, but the cron user is the real fix.
>
> Redirection to the log stays outside `sudo`, so the log file remains root-owned.

### Manual

```bash
cd /var/www/thebookswanderer.com/server
.venv/bin/python scripts/pinterest_auto_pin.py --dry-run
.venv/bin/python scripts/pinterest_auto_pin.py
.venv/bin/python scripts/pinterest_auto_pin.py --limit 2
```

Launch pin is best-effort: a Pinterest failure does **not** roll back product import.

### Two expiry clocks

| Token | Lifetime | Renewal |
|---|---|---|
| **Access** | 30 days | Automatic — refreshed 24 h before expiry |
| **Refresh** | 60 days | **Manual OAuth only.** Nothing renews it for you |

When the refresh token dies, everything returns 401 and auto-pin stops. The
daily job calls `check_token_health()` first and emails `MAIL_NOTIFY_TO` once a
day starting `PINTEREST_REAUTH_WARN_DAYS` (14) before the deadline, then daily
while expired. Fix = redo step 3 (OAuth) above.

Check anytime — neither returns secrets:

```bash
.venv/bin/python scripts/pinterest_auto_pin.py --dry-run   # includes "token" block
curl "https://thebookswanderer.com/api/pinterest/status?admin_key=..."  # "token_health"
```

---

## Security

- Never commit tokens or client secrets.
- Never reuse MathRelaxing’s **access token** on TBW.
- Prefer private OAuth start URLs (`admin_key` is a secret).
