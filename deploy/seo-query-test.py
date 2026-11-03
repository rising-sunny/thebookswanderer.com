#!/usr/bin/env python3
"""One-time, read-only test of tbw-seo-query: fresh page totals and three URL inspections."""
import json
import urllib.request

KEY = open("/etc/tbw-admin-api/key").read().strip()


def call(path, body):
    req = urllib.request.Request("http://127.0.0.1:8881" + path, data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"http": e.code, "detail": json.load(e).get("detail")}


print(json.dumps(call("/query", {"start_date": "2026-10-27", "end_date": "2026-11-02",
                                 "dimensions": ["page"], "row_limit": 15}), ensure_ascii=False)[:3000])
for url in ["https://thebookswanderer.com/guides/hold-a-book-open-one-handed/",
            "https://thebookswanderer.com/guides/gifts-for-jane-austen-fans/",
            "https://thebookswanderer.com/guides/pride-and-prejudice-first-line/"]:
    r = call("/inspect", {"url": url})
    r.pop("referring_urls", None)
    print(json.dumps(r, ensure_ascii=False)[:1200])
