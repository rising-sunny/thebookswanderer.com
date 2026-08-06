# Facebook Page posts (organic)

Publish to **The Books Wanderer** Facebook Page from this repo via Graph API.

| | |
|---|---|
| **Script** | [`server/scripts/fb_post.py`](../scripts/fb_post.py) |
| **Product helper** | [`server/scripts/post_product_fb.py`](../scripts/post_product_fb.py) |
| **Env** | `FB_PAGE_ID`, `FB_PAGE_TOKEN` in `server/.env` |

This is **not** Meta Ads MCP (campaigns). It only posts organic content as the Page.

Official Ads MCP (campaigns): `https://mcp.facebook.com/ads` — separate setup.

---

## One-time setup (any machine after clone)

1. Copy env and set Page credentials:

```powershell
cd server
copy .env.example .env
# edit .env → FB_PAGE_ID + FB_PAGE_TOKEN
```

2. Get a token:

- [Graph API Explorer](https://developers.facebook.com/tools/explorer)
- Permissions: `pages_manage_posts`, `pages_read_engagement`
- User token → `GET /me/accounts` → use the **Page** access token, or leave a user token (the script exchanges it for a Page token)
- Prefer **long-lived** token (~60 days) or System User for production VPS

3. Page ID for TBW (Business Suite): `1200587819810293`

4. Smoke test (no publish):

```powershell
cd server
.\.venv\Scripts\Activate.ps1
python scripts/fb_post.py whoami
```

---

## Commands

From `server/` (venv active, `.env` loaded):

```powershell
# Text + optional link
python scripts/fb_post.py text "Hello readers" --link https://thebookswanderer.com

# Photo (local path or public URL)
python scripts/fb_post.py photo ..\assets\logo.png --message "Caption"
python scripts/fb_post.py photo "https://example.com/img.jpg" --message "Caption"

# Carousel (several images)
python scripts/fb_post.py photo a.jpg b.jpg c.jpg --message "Swipe"

# Video
python scripts/fb_post.py video clip.mp4 --message "Caption" --title "Title"

# Schedule (local server time; 10 min – 30 days)
python scripts/fb_post.py text "Hello" --schedule "2026-08-10 10:00"

# Dry-run (global flag before subcommand)
python scripts/fb_post.py --dry-run photo img.jpg --message "Test"
```

### Promote a catalog product

Pulls title/price/image from the live API (or `--base` URL) and posts:

```powershell
# Dry-run
python scripts/post_product_fb.py hollow-kitten-bookmark --dry-run

# Publish
python scripts/post_product_fb.py hollow-kitten-bookmark

# Custom campaign UTM
python scripts/post_product_fb.py wooden-reading-tracker --campaign fb_organic_tracker
```

List slugs: open https://thebookswanderer.com/api/products

---

## VPS

Same scripts live under `/var/www/thebookswanderer.com/server/`.  
Production `.env` already has `FB_PAGE_ID` / `FB_PAGE_TOKEN`.

```bash
cd /var/www/thebookswanderer.com/server
. .venv/bin/activate
python scripts/fb_post.py whoami
python scripts/post_product_fb.py hollow-kitten-bookmark --dry-run
```

---

## Security

- Never commit `FB_PAGE_TOKEN` or real `.env`
- Tokens are scrubbed from error output in `fb_post.py`
- Prefer long-lived / system-user tokens on the VPS
