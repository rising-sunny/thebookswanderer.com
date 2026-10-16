#!/usr/bin/env python3
"""Discover new literary blogs through public links from known literary sites.

No search-engine scraping or credentials. Respect robots and private-IP blocking.
"""
from __future__ import annotations

import fcntl
import json
import argparse
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from services import collaborators_store as store
from services.collaborators import Fetcher, ResearchError, normalize_url, parse_page, site_host
import httpx

LITERARY = ("libro", "literar", "lectur", "book", "reader", "reading", "bibliotec", "novel", "poes", "poet", "reseñ", "review")
PLATFORMS = ("facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com", "pinterest.com", "amazon.com", "amazon.es", "goodreads.com", "google.com", "blogger.com", "wordpress.com", "wordpress.org", "wikipedia.org", "bookshop.org", "linktr.ee", "tiktok.com", "thebookswanderer.com", "feedburner.com", "substack.com")


def root_url(url: str) -> str:
    parsed = urlsplit(normalize_url(url))
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def literary_profile(html: str) -> dict | None:
    page = parse_page(html)
    if page.noindex:
        return None
    text = " ".join(page.parts)[:40_000].lower()
    score = sum(word in text for word in LITERARY)
    community = any(word in text for word in ("blog", "reseña", "review", "club de lectura", "book club"))
    if score < 3 or not community:
        return None
    es = len(re.findall(r"\b(libros?|lectura|reseñas?|escritor|autores|novelas?|literatura|contacto)\b", text))
    en = len(re.findall(r"\b(books?|reading|readers?|reviews?|authors?|novels?|literature|contact)\b", text))
    return {"lang": "es" if es > en else "en", "reason": "Página pública con referencias a libros, reseñas y una comunidad lectora.", "category": "Blog / comunidad de lectura"}


def candidate_links(html: str, url: str) -> list[str]:
    page = parse_page(html)
    if page.noindex or page.nofollow:
        return []
    found = []
    for href, label in page.links:
        try:
            linked = root_url(urljoin(url, href))
        except ResearchError:
            continue
        host = site_host(linked)
        if host == site_host(url) or any(host == p or (host.endswith("." + p) and p not in ("wordpress.com", "blogger.com")) for p in PLATFORMS):
            continue
        if not any(word in (host + " " + label).lower() for word in LITERARY):
            continue
        if linked not in found:
            found.append(linked)
    return found[:30]


def community_pages(html: str, url: str) -> list[str]:
    """Follow a few public blogrolls, not just links visible on the homepage."""
    page = parse_page(html)
    if page.noindex or page.nofollow:
        return []
    found = []
    for href, label in page.links:
        try:
            link = normalize_url(urljoin(url, href))
        except ResearchError:
            continue
        if site_host(link) != site_host(url) or link == url:
            continue
        if any(word in (label + ' ' + link).lower() for word in ('blogroll', 'bloggers', 'enlaces', 'friends', 'amigos', '/blogs', '/links')) and link not in found:
            found.append(link)
    return found[:2]


def run() -> dict:
    store.init_store()
    totals = {"parents": 0, "checked": 0, "added": 0, "unavailable": 0, "community_pages": 0}
    with (store.data_dir() / "discovery.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "already_running"}
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat(timespec="seconds")
        hubs = json.loads(Path(__file__).with_name('literary_discovery_hubs.json').read_text())
        with store.connect() as db:
            db.executemany('INSERT OR IGNORE INTO discovery_hubs(url) VALUES(?)', [(root_url(url),) for url in hubs])
            existing = {site_host(r['url']) for r in db.execute('SELECT url FROM sources')}
            parents = [dict(r) for r in db.execute("SELECT id,url FROM sources WHERE active=1 AND (discovery_checked_at IS NULL OR discovery_checked_at<?) ORDER BY discovery_checked_at IS NOT NULL,discovery_checked_at,id LIMIT 4", (cutoff,))]
            boot = [dict(r) for r in db.execute("SELECT url FROM discovery_hubs WHERE checked_at IS NULL OR checked_at<? ORDER BY checked_at IS NOT NULL,checked_at,url LIMIT 6", (cutoff,))]
        if len(existing) >= 250:
            return {"status": "source_limit", **totals}
        deadline = time.monotonic() + 10 * 60
        attempted = set(existing)
        def register(url, html):
            profile = literary_profile(html)
            if not profile or site_host(url) in existing or len(existing) >= 250:
                return
            with store.connect() as db:
                cursor = db.execute("INSERT OR IGNORE INTO sources(name,url,lang,category,reason,origin) VALUES(?,?,?,?,?,'auto')", (site_host(url), root_url(url), profile['lang'], profile['category'], profile['reason']))
                if cursor.rowcount:
                    totals['added'] += 1
                    existing.add(site_host(url))
        for parent in boot + parents:
            if time.monotonic() >= deadline or totals['checked'] >= 20 or totals['added'] >= 12:
                break
            url = root_url(parent['url'])
            fetcher = Fetcher(url, max_seconds=45)
            links = []
            status = 'verified'
            try:
                final, html = fetcher.page(url)
                # Bootstrap entries become sources only after their content is verified.
                register(final, html)
                links += candidate_links(html, final)
                for subpage in community_pages(html, final):
                    try:
                        subfinal, subhtml = fetcher.page(subpage)
                        totals['community_pages'] += 1
                        links += candidate_links(subhtml, subfinal)
                    except (ResearchError, httpx.HTTPError, OSError):
                        totals['unavailable'] += 1
            except (ResearchError, httpx.HTTPError, OSError):
                totals['unavailable'] += 1
                status = 'unavailable'
            finally:
                fetcher.close()
            totals['parents'] += 1
            with store.connect() as db:
                if 'id' in parent:
                    db.execute('UPDATE sources SET discovery_checked_at=? WHERE id=?', (store.now(),parent['id']))
                else:
                    db.execute('UPDATE discovery_hubs SET checked_at=?,last_status=? WHERE url=?', (store.now(),status,parent['url']))
            for link in dict.fromkeys(links):
                host = site_host(link)
                if host in attempted or host in existing:
                    continue
                if time.monotonic() >= deadline or totals['checked'] >= 20 or totals['added'] >= 12 or len(existing) >= 250:
                    break
                attempted.add(host)
                totals['checked'] += 1
                child = Fetcher(link, max_seconds=25)
                try:
                    final, html = child.page(link)
                    register(final, html)
                except (ResearchError, httpx.HTTPError, OSError):
                    totals['unavailable'] += 1
                finally:
                    child.close()
        return {'status': 'completed', **totals}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False))
