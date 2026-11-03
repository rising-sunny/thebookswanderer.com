#!/usr/bin/env python3
"""One-time, read-only Search Console exploration (last ~90 days) for new content ideas."""
import json
import urllib.request

KEY = open("/etc/tbw-admin-api/key").read().strip()


def q(body):
    req = urllib.request.Request("http://127.0.0.1:8881/query", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)["rows"]
    except urllib.error.HTTPError as e:
        print("ERR", e.code, json.load(e).get("detail")); return []


R = {"start_date": "2026-08-05", "end_date": "2026-11-02"}
print("## queries (excluding 2027 challenge)")
rows = q({**R, "dimensions": ["query"], "row_limit": 250})
for r in sorted(rows, key=lambda r: -r["impressions"]):
    if "2027" in r["query"] or "challenge" in r["query"]:
        continue
    print(f'{r["impressions"]:5} {r["clicks"]:3} {r["position"]:6.1f}  {r["query"]}')
print("## challenge-related queries (count, impressions)")
ch = [r for r in rows if "2027" in r["query"] or "challenge" in r["query"]]
print(len(ch), sum(r["impressions"] for r in ch))
for r in sorted(ch, key=lambda r: -r["impressions"])[:40]:
    print(f'{r["impressions"]:5} {r["clicks"]:3} {r["position"]:6.1f}  {r["query"]}')
print("## page x query (non-challenge pages)")
for r in sorted(q({**R, "dimensions": ["page", "query"], "row_limit": 250}), key=lambda r: -r["impressions"]):
    if "challenge" in r["page"] or "reto-de" in r["page"]:
        continue
    print(f'{r["impressions"]:5} {r["clicks"]:3} {r["position"]:6.1f}  {r["page"].replace("https://thebookswanderer.com","")}  | {r["query"]}')
print("## pages")
for r in sorted(q({**R, "dimensions": ["page"], "row_limit": 100}), key=lambda r: -r["impressions"])[:40]:
    print(f'{r["impressions"]:5} {r["clicks"]:3} {r["position"]:6.1f}  {r["page"].replace("https://thebookswanderer.com","")}')
print("## countries")
for r in q({**R, "dimensions": ["country"], "row_limit": 15}):
    print(f'{r["impressions"]:5} {r["clicks"]:3} {r["position"]:6.1f}  {r["country"]}')
print("## done")
