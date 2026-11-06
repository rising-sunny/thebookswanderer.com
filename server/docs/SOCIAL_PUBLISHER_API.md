# Private VPS photo publisher

This service lets the attached Codex cloud environment publish product photo
posts through HTTPS. It does not require SSH, Tailscale, or a separate MCP host.
It is an authenticated HTTP API, not an MCP endpoint. A connection in this cloud
environment does not automatically connect other chats or environments.

`deploy/install-social-publisher.py` embeds the API, tested photo core, and 13
offline tests. Run it with the existing VPS virtualenv. `--check` runs only the
embedded tests. Normal installation requires root and asks for a new, dedicated
ASCII key of at least 32 characters, without echoing it. Keep it in a password
manager. Do not use the Meta token, store SECRET_KEY, or paste secrets in chat.

Installation creates a www-data systemd service bound to 127.0.0.1:8877, with
code under `/opt/tbw-social-publisher` and private journals under
`/var/lib/tbw-social-publisher`. Only the two Facebook settings are copied from
the store .env to `/etc/tbw-social-publisher/meta.env` (root:www-data 0640).
The separate API key is stored alongside it. Reinstall to refresh the Meta
settings after rotating the Page token. The original store .env is untouched.

The installer adds a higher priority `/api/social-publisher/` Nginx location
in the existing site file, verifies `nginx -t`, checks authenticated local
health and rejection without credentials, then reloads Nginx. It never restarts
the shop or publishes a post. It backs up previous code and Nginx configuration
and attempts rollback on activation errors. An unfamiliar Nginx layout causes
installation to stop. Public HTTPS retrieval is verified separately.

In the attached cloud environment configuration, add a network secret named
`SOCIAL_PUBLISHER_KEY`, exposed with that variable name and restricted to
`thebookswanderer.com`. Use the same key entered during installation. Publish
the environment configuration and verify that runtime observations report it
ready before using it. Remove obsolete VPN configuration through the supported
configuration UI if it forces public HTTPS traffic through an unavailable VPN.
Keep the inherited session proxy and CA trust; do not bypass networking policy.

Use `Authorization: Bearer <SOCIAL_PUBLISHER_KEY>` on requests to
`https://thebookswanderer.com/api/social-publisher`:

- `GET /health`: read-only local readiness, never calls Meta or posts.
- `POST /drafts`: JSON with campaign, slug, facebook_caption, instagram_caption.
  Downloads the live product and owned JPEG without credentials, checks image
  size/format, and persists the exact payload. No Meta writes.
- `GET /jobs/{campaign}`: read-only saved content and network outcomes.
- `POST /jobs/{campaign}/publish`: explicitly publishes the saved draft to both
  configured networks as a photo. Returns 202; poll the job endpoint for URLs.

Each new post requires a unique campaign. Reusing a campaign with different
content returns 409. Repeated publication requests do not resubmit writes.
Interrupted jobs and uncertain remote outcomes require review. They never
automatically retry on restart. The worker verifies that the image has not
changed since draft preparation and checks the expected Facebook and linked
Instagram IDs before publishing. Credentials are sent only to Meta.

The existing daily reel automation is unchanged. This API currently supports
one existing compatible JPEG, both networks, and immediate publication only;
carousels, generated asset uploads, scheduling and selective networks are not
implemented. Keep captions within documented request limits. Request a post
in chat explicitly before invoking the publication endpoint.
