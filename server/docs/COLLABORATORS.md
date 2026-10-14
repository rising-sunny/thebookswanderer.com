# Collaborator research

Private inbox: `/admin/collaborators`, linked from Live. Uses the existing Live
administrator login. Read-only API: `/api/admin/collaborators`, authenticated by
that session or an `X-Admin-Key` header containing the existing `SECRET_KEY`.
Never put the key in a link or browser storage. Forms bind CSRF tokens to the
administrator session. Responses are private, uncached, and excluded from indexing.

## What it does

Eight initial Spanish/English literary websites are research leads, not verified
partners. The owner can add up to 250 selected sources or pause individual sites.
A daily GitHub Actions workflow (`Research collaborators`, 12:15 UTC) invokes the
collector on the VPS through the existing SSH secrets. Actions can delay schedules;
`workflow_dispatch` also permits a manual run after a successful deployment.

The collector checks at most 20 due sites, oldest first, at most once per 23 hours.
Each site gets a 75-second budget, its selected page and up to four linked
professional-contact pages. Robots rules, crawl delay, noindex, nofollow and
blocking responses are respected. Unsupported JS-only pages, obfuscated addresses,
external redirects, contact forms, private destinations and oversized pages are
not bypassed. No search engine or social network is scraped. Sources can be entered
as an exact public contact-page URL if the homepage doesn't link to it.

Only published addresses with professional-contact context are retained, with
their exact source URL, a short evidence excerpt, discovery date and last-seen
date. There is no email guessing or bulk harvesting of personal profiles.
The affinity reason is manually supplied source metadata, not a measured score.
Every new address starts pending. Rediscovery preserves review status and notes.
Pausing a source stops future collection, but retains prior candidates.

There are no mail sends or newsletter writes. Export defaults to approved records
and neutralizes spreadsheet formula injection. A published professional address
is not newsletter consent; review purpose and relevance before any outreach.

## Operations

Data and the collector lock are in `/var/lib/tbw-collaborators`, outside nginx's
web root, owned by `www-data` with mode 700. Back up `research.db` with SQLite's
backup API along with the store's normal backups. Include the new directory in
the server's private backup policy. SQLite commits each site's results separately.
A process lock prevents concurrent Actions or manually dispatched script runs.
Interrupted runs are marked when the next collector acquires the lock.

```sh
cd /var/www/thebookswanderer.com/server
runuser -u www-data -- .venv/bin/python scripts/collect_collaborators.py --dry-run
runuser -u www-data -- .venv/bin/python scripts/collect_collaborators.py --limit 20
# Explicitly revisit recently checked sources:
runuser -u www-data -- .venv/bin/python scripts/collect_collaborators.py --force
```

`Run server script` can also invoke `collect_collaborators.py` using the existing
workflow. Logs show aggregate counts, not addresses or downloaded pages.
`COLLABORATORS_DATA_DIR` overrides the storage directory for isolated local tests;
production should keep the default outside the web root. No new credentials,
Tailscale, search service, or email provider are needed.

Direct fetches pin public DNS answers to socket destinations, preserving hostname
verification for TLS. If an environment proxy is configured it is retained and
the destination is also checked; the trusted proxy enforces its own DNS/egress
policy. Review this adapter when upgrading the pinned httpx dependency.
