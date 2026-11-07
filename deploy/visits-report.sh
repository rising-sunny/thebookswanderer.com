#!/bin/bash
# One-time, read-only: where the site's visits come from (owner request 2026-11-07).
# Aggregates from the first-party live_events table only; no IPs, cities, sessions or emails are printed.
cd /var/www/thebookswanderer.com/server && runuser -u www-data -- .venv/bin/python - <<'PY'
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from urllib.parse import urlsplit
from database import SessionLocal
from models import LiveEvent

SKIP = ("bot", "server", "crawler", "spider")
db = SessionLocal()
t0 = datetime.utcnow() - timedelta(days=14)
rows = db.query(LiveEvent.ts, LiveEvent.session_id, LiveEvent.event_type, LiveEvent.path, LiveEvent.referrer_domain,
                LiveEvent.source, LiveEvent.medium, LiveEvent.campaign, LiveEvent.country, LiveEvent.ua_class
                ).filter(LiveEvent.ts >= t0).all()
print("== events since", t0.date(), ":", len(rows), "| ua classes:", dict(Counter((r.ua_class or "?") for r in rows)))
rows = [r for r in rows if not any(k in (r.ua_class or "").lower() for k in SKIP)]
pv = [r for r in rows if r.event_type == "pageview"]
def grp(r):
    s = (r.source or "").lower() or (r.referrer_domain or "").lower().removeprefix("www.")
    if r.medium and r.source: s += " [" + r.medium.lower() + "]"
    return s or "direct"
def page(r): return urlsplit(r.path or "").path[:60] or "/"
def sess(rs): return len({r.session_id for r in rs})
print("== human pageviews:", len(pv), "| sessions:", sess(pv))
d = defaultdict(list)
for r in pv: d[r.ts.date()].append(r)
print("== per day (sessions / pageviews)")
for k in sorted(d): print("  ", k, sess(d[k]), len(d[k]))
for title, key in (("source", grp), ("landing page", page), ("country", lambda r: r.country or "?")):
    g = defaultdict(list)
    for r in pv: g[key(r)].append(r)
    print(f"== by {title} (sessions / pageviews), top 15")
    for k, v in sorted(g.items(), key=lambda kv: -sess(kv[1]))[:15]: print(f"   {k[:50]:50} {sess(v):5} {len(v):5}")
last7 = datetime.utcnow() - timedelta(days=7)
g = defaultdict(list)
for r in pv:
    if r.ts >= last7: g[(grp(r), page(r))].append(r)
print("== last 7 days: source -> page (sessions), top 15")
for k, v in sorted(g.items(), key=lambda kv: -sess(kv[1]))[:15]: print(f"   {k[0][:28]:28} {k[1][:44]:44} {sess(v):4}")
camp = Counter(r.campaign for r in pv if r.campaign)
print("== campaigns (pageviews):", dict(camp.most_common(8)))
print("== funnel events, last 14 days:", dict(Counter(r.event_type for r in rows if r.event_type != "pageview")))
db.close()
PY
