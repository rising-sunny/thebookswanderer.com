# Autonomous marketing operations

All jobs run as `www-data`, using the existing server configuration. Deploy
through GitHub Actions; `Run server script` is the manual maintenance entry point.

## Pinterest

Supplier-specific destination text replaces worldwide shipping claims. Lulu uses
`LULU_SHIP_COUNTRIES`; Printify is US only; PDFs have no physical shipping.
`repair_marketing_pins.py --apply` updates old restricted-product descriptions
without changing pin images, variant titles or links, and backfills active
products that have no recorded pin. Default invocation only plans changes.

The database retains old duplicate rows as `duplicate`, excluded from active
counts. A partial unique index and idempotent recording prevent duplicate active
Pinterest IDs. This does not delete any Pinterest publication.

## Reader discovery and invitations

`run_reader_outreach.py --send` runs daily at 12:15 UTC on the VPS. GitHub's
manual workflow calls the same locked job; its former schedule is removed.

The crawler rotates 16 bootstrap sites plus verified existing sources and follows
bounded public blogroll pages. A bootstrap URL becomes a source only after its
literary content is verified. Robots rules, host/IP checks, page/time limits,
noindex/nofollow, the 250-source cap, and professional-context extraction remain.
Each run adds at most 12 sites and examines at most 20 linked candidates.

Invitations use hello@thebookswanderer.com, at most 10 attempts per rolling
24 hours, once per email/site across campaigns. Previous opt-outs, subscribers,
requested sample addresses, and ambiguous prior attempts are excluded.

## Monthly subscriber letter

First issue: November 2026. `send_monthly_newsletter.py --send` runs at 12:35 UTC
on days 1–3. Later runs catch up unsent recipients; each address can receive the
issue only once. The default CLI invocation is a dry run.

Only active newsletter subscribers who completed the welcome series at least
seven days earlier qualify. Outreach contacts are not subscribed automatically.
Test/sample sources, requested sample addresses and unsubscribes are excluded.
The private research database holds a unique `(period,email)` delivery ledger.
Ambiguous SMTP attempts are not automatically retried. Recipients are checked
again before delivery. This letter has its own subscriber unsubscribe link.

Each issue uses a seasonal reading prompt, a rotating active-product selection,
and the free Reading Challenge. English and Spanish previews are available to
administrators at `/admin/newsletter/monthly-preview?lang=en` or `lang=es`.
No monthly broadcast is sent during installation or preview.

## Verification

`marketing_status.py` reports aggregate counts, installed schedules, duplicate
checks, exclusions and current shipping copy without printing email addresses.
The regression suite uses temporary databases and mocked SMTP/provider calls.

### Pinterest application restriction

If Pinterest rejects PATCH with HTTP 401 / code 3 / `pin_edit`, the repair
command stops attempting edits, finishes its backfill work, saves a private
copy plan, and exits 2 to report the partial result. It does not delete or
recreate existing pins. Administrators can copy the exact replacement text at
`/admin/pinterest/copy-repairs`; enabling `pin_edit` requires Pinterest app access.
