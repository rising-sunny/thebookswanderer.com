# Pinterest — The Books Wanderer (own app)

Publish product pins via **Pinterest API v5** with a **dedicated app** for this shop (not MathRelaxing’s app).

| | |
|---|---|
| **Service** | [`server/services/pinterest.py`](../services/pinterest.py) |
| **HTTP routes** | [`server/routers/pinterest.py`](../routers/pinterest.py) |
| **CLI** | [`server/scripts/pinterest_cli.py`](../scripts/pinterest_cli.py) |
| **Token file** | `server/data/.pinterest_token.json` (or `PINTEREST_TOKEN_FILE`) |

---

## One-time: create a new Pinterest app (option B)

1. Open [Pinterest Developers](https://developers.pinterest.com/) while logged into the **The Books Wanderer** business account (or the Google/Pinterest account that owns that profile).
2. **Create app** → name it e.g. `The Books Wanderer` / `TBW Store`.
3. Under **Configure** / OAuth / Redirect URIs, add **exactly**:
   ```
   https://thebookswanderer.com/api/pinterest/oauth/callback
   ```
4. Request / enable scopes (trial or standard as available):
   - `boards:read`, `boards:write`
   - `pins:read`, `pins:write`
   - `user_accounts:read`, `user_accounts:write`
5. Copy **App ID** → `PINTEREST_CLIENT_ID`
6. Copy **App secret** → `PINTEREST_CLIENT_SECRET`

Do **not** reuse MathRelaxing’s client id/secret if you want a clean separation.

---

## Env (`server/.env`)

```env
PINTEREST_CLIENT_ID=
PINTEREST_CLIENT_SECRET=
PINTEREST_REDIRECT_URI=https://thebookswanderer.com/api/pinterest/oauth/callback
PINTEREST_SCOPES=boards:read,boards:write,pins:read,pins:write,user_accounts:read,user_accounts:write
PINTEREST_API_BASE=https://api.pinterest.com/v5
# Optional overrides:
# PINTEREST_TOKEN_FILE=/var/www/thebookswanderer.com/server/data/.pinterest_token.json
# PINTEREST_STATE_SECRET=long-random-string
```

`SECRET_KEY` (already used for admin APIs) protects OAuth start / status / pin endpoints.

On the VPS, put the same vars in `/var/www/thebookswanderer.com/server/.env`, then:

```bash
systemctl restart thebookswanderer
```

---

## Connect the TBW Pinterest account (OAuth)

1. In the browser: **log out** of MathRelaxing / any other Pinterest profile (or use a private window).
2. Log in as **The Books Wanderer**.
3. Open (replace with your real `SECRET_KEY` from `.env`):

   ```
   https://thebookswanderer.com/api/pinterest/oauth/start?admin_key=YOUR_SECRET_KEY
   ```

4. Approve the permissions.
5. You should land on a “Pinterest connected” page; token is written to `server/data/.pinterest_token.json`.

Or print the same URL locally:

```powershell
cd server
.\.venv\Scripts\Activate.ps1
python scripts/pinterest_cli.py oauth-url
```

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

## Claim the website (optional, separate from API)

In Pinterest Business → **Settings → Claimed accounts → Websites**:

1. Add `thebookswanderer.com`
2. Choose meta tag or HTML file verification
3. Deploy the tag/file on TBW and confirm

This proves domain ownership (rich pins / branding). It does **not** replace OAuth for the API.

---

## Security

- Never commit `.pinterest_token.json` or real client secrets.
- Prefer a long `SECRET_KEY`; do not paste OAuth start URLs in public chats.
- Rotate app secret in Developers if it leaks.
