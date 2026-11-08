#!/bin/bash
# One-time, read-only: where the site's visits come from (owner request 2026-11-07). v2: also drops datacenter traffic. v3 (2026-11-08): funnel by channel.
# Aggregates from the first-party live_events table only; no IPs, cities, sessions or emails are printed.
cd /var/www/thebookswanderer.com/server && runuser -u www-data -- .venv/bin/python - <<'PY'
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from urllib.parse import urlsplit
from database import SessionLocal
from models import LiveEvent

SKIP = ("bot", "server", "crawler", "spider", "datacenter", "hosting")
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
AI = ("chatgpt", "openai", "perplexity", "gemini", "claude", "copilot", "you.com", "phind", "kagi")
ai = [r for r in pv if any(k in grp(r) for k in AI)]
print("== AI assistants: sessions", sess(ai), "| pageviews", len(ai))
g = defaultdict(list)
for r in ai: g[(grp(r), page(r))].append(r)
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:15]: print(f"   {k[0][:24]:24} {k[1][:48]:48} sessions {sess(v)} views {len(v)}")
print("== ai daily:", {str(k): sess(v) for k, v in sorted(defaultdict(list, {d: [r for r in ai if r.ts.date() == d] for d in {r.ts.date() for r in ai}}).items())})
print("== pages per session by source group:")
sg = defaultdict(list)
for r in pv: sg[grp(r)].append(r)
for k, v in sorted(sg.items(), key=lambda kv: -sess(kv[1]))[:8]: print(f"   {k[:36]:36} {sess(v):4} sessions  {len(v)/max(sess(v),1):.1f} pages/session")
camp = Counter(r.campaign for r in pv if r.campaign)
print("== campaigns (pageviews):", dict(camp.most_common(8)))
print("== funnel events, last 14 days:", dict(Counter(r.event_type for r in rows if r.event_type != "pageview")))
# --- v3: funnel by channel (session first touch), human traffic only, aggregates only ---
PAID = {"paid", "cpc", "ppc", "paid_social", "paidsocial", "paid-social"}
SEARCH = ("google", "bing", "duckduckgo", "yahoo", "ecosia", "brave", "yandex", "baidu", "startpage", "qwant")
SOCIAL = ("facebook", "instagram", "pinterest", "reddit", "youtube", "tiktok", "twitter", "t.co", "x.com", "linkedin")
def channel(r):
    g, m = grp(r), (r.medium or "").lower()
    if m in PAID or "paid" in m or "cpc" in m: return "paid ads"
    if any(k in g for k in AI): return "AI assistants"
    if any(k in g for k in SEARCH): return "organic search"
    if any(k in g for k in SOCIAL): return "social (unpaid)"
    return "direct / unknown" if g == "direct" else "other referral"
first = {}
for r in sorted(pv, key=lambda r: r.ts): first.setdefault(r.session_id, r)
chan = {sid: channel(r) for sid, r in first.items()}
by_ev = defaultdict(lambda: defaultdict(set))
for r in rows:
    if r.session_id in chan and r.event_type != "pageview": by_ev[r.event_type][chan[r.session_id]].add(r.session_id)
cs = Counter(chan.values())
types = ["product_view", "add_to_cart", "checkout_start", "purchase_return"]
print("== v3 FUNNEL BY CHANNEL, last 14 days (sessions, by first touch)")
print("   " + "channel".ljust(20) + "sessions".rjust(9) + "".join(t[:12].rjust(14) for t in types))
for ch, n in cs.most_common():
    print("   " + ch.ljust(20) + str(n).rjust(9) + "".join(str(len(by_ev[t][ch])).rjust(14) for t in types))
print("== v3 top 5 landing pages per channel (sessions)")
for ch, _ in cs.most_common():
    gl = Counter(page(first[sid]) for sid, c in chan.items() if c == ch)
    print("   " + ch + ": " + "; ".join(f"{k[:40]} {v}" for k, v in gl.most_common(5)))
print("== v3 product pages viewed per channel (sessions), top 5")
for ch, _ in cs.most_common():
    pc = defaultdict(set)
    for r in rows:
        if r.event_type == "product_view" and chan.get(r.session_id) == ch: pc[page(r)].add(r.session_id)
    print("   " + ch + ": " + "; ".join(f"{k[:44]} {len(v)}" for k, v in sorted(pc.items(), key=lambda kv: -len(kv[1]))[:5]))
db.close()
PY
