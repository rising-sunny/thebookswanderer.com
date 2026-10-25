# Owner-only MCP bridge

FastMCP 4.1.2 with GitHub OAuth, required scope read:user, explicit consent
and account-ID validation for rising-sunny (243996697).
Provider credentials remain on the VPS. No repository permissions are requested.

The planned MCP URL is https://thebookswanderer.com/mcp.
GitHub callback: https://thebookswanderer.com/mcp-oauth/callback.
OAuth client redirects are restricted to HTTPS chatgpt.com and chat.openai.com,
the claude.ai/claude.com connector callback and loopback ports for CLI clients.
CIMD is disabled; downstream clients can use dynamic registration.

Store product reads, CJ, Printify and Prodigi catalog reads, shipping quotes
(any supplier, Lulu included), the supplier API pass-through (tbw_supplier_get;
tbw_supplier_write needs the code from its own preview), cross-listing with
Etsy (tbw_draft_from_etsy, tbw_publish_to_etsy) and CJ drafts are exposed: tbw_preview_draft, tbw_create_draft, tbw_update_draft (English and
Spanish copy), tbw_delete_draft, tbw_preview_publish / tbw_publish_draft and
tbw_preview_unpublish / tbw_unpublish_product (both need the code shown by
their preview, which changes after any edit).
There are no publication, deletion, real-order, wallet or execution tools.

Runtime credentials are delivered by systemd LoadCredential:
- oauth_config from /etc/tbw-mcp/oauth.json
- admin_key from /etc/tbw-admin-api/key

OAuth state is persisted under /var/lib/tbw-mcp/oauth using the library's
FileTreeStore and FernetEncryptionWrapper. The random signing secret also
derives a domain-separated storage key. Never commit credentials or state.

The bridge calls only the local restricted administrative API on port 8878.
Provider keys are not loaded by the MCP service.
The MCP listener will bind to 127.0.0.1:8879.

Tests use fake credentials, temporary encrypted stores, mocked GitHub
verification and mocked local API responses. No external requests are made.
Run test_tbw_mcp.py with the isolated MCP virtualenv.

On an existing installation, upgrade admin-api first, then run
install.py --upgrade --check and install.py --upgrade. It replaces only the
code, restarts tbw-mcp and restores the previous code if discovery fails.
Creating this PR does not publish a service or authorize this chat.
