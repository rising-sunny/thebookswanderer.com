# Owner-only MCP bridge

FastMCP 4.1.2 with GitHub OAuth, required scope read:user, explicit consent
and account-ID validation for rising-sunny (243996697).
Provider credentials remain on the VPS. No repository permissions are requested.

The planned MCP URL is https://thebookswanderer.com/mcp.
GitHub callback: https://thebookswanderer.com/mcp-oauth/callback.
OAuth client redirects are restricted to HTTPS chatgpt.com and chat.openai.com.
CIMD is disabled; downstream clients can use dynamic registration.

Only product reads and isolated Qikink draft operations are exposed.
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

Installation, HTTPS discovery and a real owner OAuth login are pending.
Creating this PR does not publish a service or authorize this chat.

## Read-only Qikink catalog lookup

`tbw_search_qikink_catalog(query="bookmark", limit=5)` calls only
`GET /qikink/catalog` on the local administrative service. `sku` is an optional
exact, case-sensitive filter; `query` matches all words against title, variant
and SKU, without case sensitivity. Results are paginated and include total.
The tool does not call the supplier or load its credentials.

This first implementation reads an operator-supplied catalog snapshot, **not a
live Qikink catalog API**. No catalog endpoint was confirmed. The supplied
Qikink Orders 08-25 documentation covers tokens and orders, not catalog lookup.
Order history is not a catalog and is deliberately not queried.
See ../admin-api/README.md for the snapshot format and activation procedure.
Missing/invalid snapshots produce an error, never an invented SKU or an empty
success. Results expose their source, retrieval date and `live_verified=false`.
They cannot establish stock, price, print compatibility or order readiness.

This change is based on PR #93 and must follow that change through review.
No deployment, token rotation or change of OAuth scopes is included.
