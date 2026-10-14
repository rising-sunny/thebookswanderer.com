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

The research collector itself never sends mail or writes newsletter records. Export defaults to approved records
and neutralizes spreadsheet formula injection. A published professional address
is not newsletter consent; review purpose and relevance before any outreach.

## Email draft preview

`/admin/collaborators/email-preview` shows a bilingual, branded shop invitation
with a direct newsletter-signup link for the existing free 2027 Reading Challenge.
Each inbox candidate links to a preview with its recipient and language.
The preview supports HTML download and a plain-text version. It uses the existing
Live session and private response headers. It performs no sending, scheduling,
candidate-state changes, or newsletter writes. Actual sends use the same approved
copy and include a signed unsubscribe link in the footer.

## Autonomous invitation campaign

The owner authorized autonomous discovery and sending. The daily Actions workflow
first runs `discover_literary_sources.py`, then `collect_collaborators.py`, then
`send_store_invitations.py --campaign store-invitation --auto --send`.

Discovery follows public links from known literary sites, checks the linked
homepage for book/review/community relevance, and determines Spanish or English
from its visible text. It does not scrape search results or private social
profiles and needs no search API key. Up to six parent sites, twelve linked
homepages and eight additions per execution are permitted. Robots directives,
public-address validation and time budgets still apply. This is bounded link
discovery; it does not search the entire web or guarantee a new match every day.

Invitations use `hello@thebookswanderer.com` for From and Reply-To, with the
existing SMTP account. TLS authentication and SMTP acceptance of that envelope
sender are checked before queueing. No invitation subscribes its recipient.
The sender selects at most one address per source, preferring the site's own
professional-domain mailbox, and checks source activity, review exclusions,
fresh evidence, previous invitations, existing subscriptions and global opt-outs.
New candidates are selected automatically under the owner's authorization;
discarded contacts and paused sources are never selected.

The private delivery ledger records the exact subject, HTML/text, stable
Message-ID and SMTP outcome. Email and site identities are checked across all
campaign labels; relabeling cannot repeat a shop invitation. A process lock and
committed pre-send claim prevent concurrent duplicates. No more than ten SMTP
attempts are made in a rolling 24 hours. Ambiguous outcomes and interrupted
attempts require review and are never retried automatically.

Each message has a signed, cookie-free unsubscribe link and List-Unsubscribe
headers. GET shows confirmation without changing state (for link scanners);
POST applies the opt-out and supports one-click email-provider requests. Both
the private suppression and existing global marketing opt-out are recorded.
Replies requesting no contact can be handled by discarding the candidate in the
panel; mailbox replies are not automatically read by this implementation.

For a preflight without sending, use Actions `Run server script` with
`send_store_invitations.py` and `--campaign store-invitation --auto`.
For an immediate authorized cycle, dispatch `collect-collaborators.yml`.
Disable that workflow in Actions to stop autonomous processing; pausing sources
or discarding individual candidates excludes those contacts. Re-enable only
within the owner's intended campaign scope.

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
