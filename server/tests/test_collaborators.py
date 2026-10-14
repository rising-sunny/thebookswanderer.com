"""Offline security, extraction, persistence and admin workflow tests."""
import csv
import io
import os
import re
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import collaborators as research
from services import collaborators_store as store
from routers.collaborators import router, csv_cell
from live import ADMIN_COOKIE, _make_cookie, _cookie_sig

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_collaborators as worker


class ExtractionTests(unittest.TestCase):
    def test_collects_explicit_professional_context_and_decodes_html(self):
        page = '<h1>Colaboraciones</h1><p>Escríbenos a alianzas&#64;literatura-real.es</p>'
        items = research.extract_contacts(page, "https://literatura-real.es/contacto/")
        self.assertEqual(items[0]["email"], "alianzas@literatura-real.es")
        self.assertEqual(items[0]["source_url"], "https://literatura-real.es/contacto/")

    def test_deduplicates_mailto_and_visible_address(self):
        page = '<p>Contact our editorial team: <a href="mailto:editorial@realbooks.org?subject=Hi">editorial@realbooks.org</a></p>'
        self.assertEqual(len(research.extract_contacts(page, "https://realbooks.org/contact")), 1)

    def test_rejects_scripts_legal_support_examples_and_unrelated_personal_email(self):
        page = '<script>contact: secret@realbooks.org</script><p>support@realbooks.org privacy@realbooks.org hello@example.com</p>'
        self.assertEqual(research.extract_contacts(page, "https://realbooks.org/contact"), [])
        self.assertEqual(research.extract_contacts('<p>Reviewer: person@gmail.com</p>', "https://realbooks.org/review"), [])
        self.assertEqual(research.extract_contacts('<p>Contact: hello@realbooks.org</p>', "https://realbooks.org/privacy"), [])

    def test_gmail_allowed_only_with_published_professional_context(self):
        items = research.extract_contacts('<p>Para colaboraciones: blogliterario@gmail.com</p>', "https://realbooks.org/contact")
        self.assertEqual(items[0]["email"], "blogliterario@gmail.com")

    def test_meta_noindex_is_respected(self):
        self.assertEqual(research.extract_contacts('<meta name="robots" content="noindex"><p>Contact: hello@realbooks.org</p>', "https://realbooks.org/contact"), [])

    def test_icon_mailto_has_evidence_without_inventing_professional_context(self):
        page = '<a href="mailto:contact@realbooks.org"><img src="email.png"></a>'
        items = research.extract_contacts(page, "https://realbooks.org/contact")
        self.assertIn("Enlace mailto publicado", items[0]["evidence"])
        self.assertEqual(research.extract_contacts(page, "https://realbooks.org/"), [])

    def test_icon_mailto_does_not_replace_meaningful_visible_evidence(self):
        page = '<p>Para colaboraciones con nuestra editorial, contact@realbooks.org</p><a href="mailto:contact@realbooks.org"><img src="email.png"></a>'
        items = research.extract_contacts(page, "https://realbooks.org/contact")
        self.assertIn("Para colaboraciones", items[0]["evidence"])

    def test_site_visits_only_four_same_site_contact_links(self):
        visited = []
        home = ''.join(f'<a href="/contact/{i}">Contact</a>' for i in range(10)) + '<a href="https://external.org/contact">Contact</a>'
        class FakeFetcher:
            def __init__(self, url): pass
            def page(self, url):
                visited.append(url)
                return url, home if url == "https://realbooks.org/" else '<p>Contact: hello@realbooks.org</p>'
            def close(self): pass
        with patch.object(research, "Fetcher", FakeFetcher):
            items, message = research.collect_site({"url": "https://realbooks.org/"})
        self.assertEqual(len(visited), 5)
        self.assertTrue(all(url.startswith("https://realbooks.org/") for url in visited))
        self.assertEqual(len(items), 1)


class NetworkTests(unittest.TestCase):
    def test_rejects_private_and_non_web_urls(self):
        for url in ("http://localhost/", "http://127.0.0.1/", "http://169.254.169.254/", "https://10.0.0.2", "http://100.64.0.1", "http://224.0.0.1", "file:///etc/passwd", "https://u:p@realbooks.org/", "https://realbooks.org:22/", "https://realbooks.org\\@127.0.0.1/"):
            with self.subTest(url=url), self.assertRaises(research.ResearchError):
                research.normalize_url(url)

    def test_dns_rejects_mixed_public_private_answers(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ("93.184.216.34", "127.0.0.1")]
        with patch.object(research.socket, "getaddrinfo", return_value=answers), self.assertRaises(research.ResearchError):
            research.public_addresses("realbooks.org", 443)

    def test_direct_socket_uses_vetted_ip_preserving_hostname_at_protocol_layer(self):
        with patch.object(research, "public_addresses", return_value=["93.184.216.34"]), patch.object(research.httpcore.SyncBackend, "connect_tcp", return_value="stream") as connect:
            result = research.PublicBackend().connect_tcp("realbooks.org", 443, timeout=2)
            self.assertEqual(result, "stream")
            self.assertEqual(connect.call_args.args[:2], ("93.184.216.34", 443))

    def fetcher(self, handler):
        fetcher = research.Fetcher("https://realbooks.org/")
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        fetcher.delay = 0
        self.addCleanup(fetcher.close)
        return fetcher, client

    @patch.object(research, "public_addresses", return_value=["93.184.216.34"])
    def test_robots_block_prevents_content_request(self, _):
        seen = []
        def respond(request):
            seen.append(request.url.path)
            return httpx.Response(200, text="User-agent: *\nDisallow: /contact\n", headers={"content-type": "text/plain"})
        fetcher, client = self.fetcher(respond)
        with patch.object(fetcher, "_client", return_value=client), self.assertRaises(research.ResearchError):
            fetcher.page("https://realbooks.org/contact")
        self.assertEqual(seen, ["/robots.txt"])

    @patch.object(research, "public_addresses", return_value=["93.184.216.34"])
    def test_private_redirect_is_never_requested(self, _):
        seen = []
        def respond(request):
            seen.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        fetcher, client = self.fetcher(respond)
        with patch.object(fetcher, "_client", return_value=client), self.assertRaises(research.ResearchError):
            fetcher.page("https://realbooks.org/contact")
        self.assertFalse(any("169.254" in url for url in seen))

    @patch.object(research, "public_addresses", return_value=["93.184.216.34"])
    def test_redirect_target_robots_are_checked(self, _):
        seen = []
        def respond(request):
            seen.append(request.url.path)
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /private", headers={"content-type": "text/plain"})
            return httpx.Response(302, headers={"location": "/private"})
        fetcher, client = self.fetcher(respond)
        with patch.object(fetcher, "_client", return_value=client), self.assertRaises(research.ResearchError):
            fetcher.page("https://realbooks.org/contact")
        self.assertNotIn("/private", seen)

    @patch.object(research, "public_addresses", return_value=["93.184.216.34"])
    def test_robots_failure_fails_closed(self, _):
        fetcher, client = self.fetcher(lambda r: httpx.Response(503))
        with patch.object(fetcher, "_client", return_value=client), self.assertRaises(research.ResearchError):
            fetcher.page("https://realbooks.org/")

    @patch.object(research, "public_addresses", return_value=["93.184.216.34"])
    def test_robots_redirect_does_not_recurse(self, _):
        def respond(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(302, headers={"location": "/robot-policy"})
            return httpx.Response(200, text="User-agent: *\nDisallow: /contact", headers={"content-type": "text/plain"})
        fetcher, client = self.fetcher(respond)
        with patch.object(fetcher, "_client", return_value=client):
            self.assertFalse(fetcher.allowed("https://realbooks.org/contact"))

    @patch.object(research, "public_addresses", return_value=["93.184.216.34"])
    def test_oversized_pages_are_rejected(self, _):
        fetcher, client = self.fetcher(lambda r: httpx.Response(200, text="x" * (research.MAX_BYTES + 1), headers={"content-type": "text/html"}))
        with patch.object(fetcher, "_client", return_value=client), self.assertRaises(research.ResearchError):
            fetcher._get("https://realbooks.org/contact")


class StoreAndAdminTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"COLLABORATORS_DATA_DIR": folder.name, "SECRET_KEY": "test-api-key", "LIVE_ADMIN_PASSWORD": "test-password", "LIVE_ADMIN_USER": "tbw"})
        env.start()
        self.addCleanup(env.stop)
        store.init_store()
        with store.connect() as db:
            self.source = db.execute("INSERT INTO sources(name,url,lang,category,reason) VALUES(?,?,?,?,?)", ("Real Books", "https://realbooks.org/", "en", "Blog", "Literary reviews")).lastrowid
            store.save_candidate(db, self.source, {"email": "hello@realbooks.org", "source_url": "https://realbooks.org/contact", "evidence": "Contact our team", "purpose": "Contact"})
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app, base_url="https://thebookswanderer.com")
        self.addCleanup(self.client.close)

    def login(self):
        self.client.cookies.set(ADMIN_COOKIE, _make_cookie("tbw"))

    def test_private_inbox_api_and_export_require_authentication(self):
        self.assertEqual(self.client.get("/admin/collaborators", follow_redirects=False).status_code, 303)
        for path in ("/api/admin/collaborators", "/admin/collaborators/export.csv"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("hello@realbooks.org", response.text)

    def test_api_key_read_and_no_query_string_key(self):
        path = "/api/admin/collaborators"
        self.assertEqual(self.client.get(path + "?admin_key=test-api-key").status_code, 401)
        response = self.client.get(path, headers={"X-Admin-Key": "test-api-key"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(response.json()["candidates"][0]["email"], "hello@realbooks.org")

    def test_email_preview_languages_formats_and_no_sending(self):
        self.login()
        before = store.snapshot()
        with patch("services.email._send_sync") as send:
            for lang in ("es", "en"):
                for format in ("view", "html", "download", "text"):
                    response = self.client.get(f"/admin/collaborators/email-preview?candidate_id=1&lang={lang}&format={format}")
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("no-store", response.headers["cache-control"])
                    self.assertNotIn("test-api-key", response.text)
                    self.assertIn("Real Books", response.text)
                    if format == "html":
                        self.assertIn(f'<html lang="{lang}">', response.text)
                        self.assertNotIn("placed an order", response.text)
                    if format == "download":
                        self.assertIn("attachment", response.headers["content-disposition"])
            send.assert_not_called()
        self.assertEqual(before, store.snapshot())

    def test_email_preview_requires_authentication_and_escapes_source_name(self):
        for format in ("view", "html", "text", "download"):
            self.assertEqual(self.client.get(f"/admin/collaborators/email-preview?format={format}", follow_redirects=False).status_code, 303)
        with store.connect() as db:
            db.execute("UPDATE sources SET name=?", ('<script>alert("xss")</script>',))
        self.login()
        response = self.client.get("/admin/collaborators/email-preview?candidate_id=1&format=html")
        self.assertNotIn('<script>alert("xss")</script>', response.text)
        self.assertIn("&lt;script&gt;", response.text)

    def test_cookie_login_csrf_and_review_preserved_on_rediscovery(self):
        self.login()
        page = self.client.get("/admin/collaborators")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("test-api-key", page.text)
        self.assertNotIn("test-password", page.text)
        token = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
        url = "/admin/collaborators/candidates/1"
        self.assertEqual(self.client.post(url, data={"status": "approved"}).status_code, 403)
        response = self.client.post(url, data={"status": "approved", "notes": "Good fit", "csrf": token}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with store.connect() as db:
            self.assertFalse(store.save_candidate(db, self.source, {"email": "hello@realbooks.org", "source_url": "https://realbooks.org/contact", "evidence": "New context", "purpose": "Contact"}))
        candidate = store.snapshot()["candidates"][0]
        self.assertEqual((candidate["status"], candidate["notes"]), ("approved", "Good fit"))
        self.assertEqual(candidate["evidence"], "New context")

    def test_cookie_fails_closed_without_password_and_for_future_timestamp(self):
        self.login()
        with patch.dict(os.environ, {"LIVE_ADMIN_PASSWORD": ""}):
            self.assertEqual(self.client.get("/api/admin/collaborators").status_code, 401)
        stamp = int(time.time()) + 3600
        self.client.cookies.set(ADMIN_COOKIE, f"{stamp}.tbw.{_cookie_sig(stamp, 'tbw')}")
        self.assertEqual(self.client.get("/api/admin/collaborators").status_code, 401)

    def test_template_escapes_collected_content(self):
        with store.connect() as db:
            db.execute("UPDATE candidates SET evidence=?", ('<script>alert("xss")</script>',))
        self.login()
        page = self.client.get("/admin/collaborators").text
        self.assertNotIn('<script>alert("xss")</script>', page)
        self.assertIn("&lt;script&gt;", page)

    def test_export_defaults_to_approved_and_neutralizes_formulas(self):
        headers = {"X-Admin-Key": "test-api-key"}
        response = self.client.get("/admin/collaborators/export.csv", headers=headers)
        self.assertNotIn("hello@realbooks.org", response.text)
        with store.connect() as db:
            db.execute("UPDATE candidates SET status='approved',notes=?", (' =HYPERLINK("evil")',))
        response = self.client.get("/admin/collaborators/export.csv", headers=headers)
        rows = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))
        self.assertIn("hello@realbooks.org", rows[1])
        self.assertIn("' =HYPERLINK(\"evil\")", rows[1])
        self.assertEqual(csv_cell("@cmd"), "'@cmd")

    def test_add_pause_source_and_invalid_urls(self):
        headers = {"X-Admin-Key": "test-api-key"}
        data = {"name": "Otro blog", "url": "http://127.0.0.1/", "lang": "es", "category": "Blog", "reason": "Lectores"}
        self.assertEqual(self.client.post("/admin/collaborators/sources", data=data, headers=headers).status_code, 400)
        data["url"] = "https://otroblog.org/contacto/"
        self.assertEqual(self.client.post("/admin/collaborators/sources", data=data, headers=headers, follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.post("/admin/collaborators/sources/2", data={"active": 0}, headers=headers, follow_redirects=False).status_code, 303)
        self.assertEqual(store.snapshot()["sources"][1]["active"] if store.snapshot()["sources"][1]["id"] == 2 else store.snapshot()["sources"][0]["active"], 0)

    def test_worker_due_rotation_errors_and_no_duplicate_contacts(self):
        item = {"email": "editorial@realbooks.org", "source_url": "https://realbooks.org/contact", "evidence": "Editorial contact", "purpose": "Contact"}
        with patch.object(worker, "collect_site", return_value=([item], "OK")) as collect:
            result = worker.run()
            self.assertEqual((result["sites"], result["added"]), (1, 1))
            self.assertEqual(worker.run()["sites"], 0)
            self.assertEqual(worker.run(force=True)["added"], 0)
            self.assertEqual(collect.call_count, 2)
        with patch.object(worker, "collect_site", side_effect=httpx.ConnectError("sensitive-network-detail")):
            self.assertEqual(worker.run(force=True)["errors"], 1)
        self.assertNotIn("sensitive-network-detail", str(store.snapshot()))

    def test_dry_run_never_contacts_sources(self):
        with patch.object(worker, "collect_site") as collect:
            self.assertEqual(worker.run(dry_run=True)["sites_due"], 1)
            collect.assert_not_called()

    def test_seed_list_is_idempotent_and_keeps_paused_sources(self):
        self.assertEqual(store.seed_sources(), 8)
        with store.connect() as db:
            db.execute("UPDATE sources SET active=0")
        self.assertEqual(store.seed_sources(), 0)
        self.assertTrue(all(not source["active"] for source in store.snapshot()["sources"]))

    def test_export_is_not_truncated_at_inbox_display_limit(self):
        with store.connect() as db:
            for i in range(505):
                store.save_candidate(db, self.source, {"email": f"team{i}@realbooks.org", "source_url": "https://realbooks.org/contact", "evidence": "Contact", "purpose": "Contact"})
            db.execute("UPDATE candidates SET status='approved'")
        self.assertEqual(len(store.snapshot()["candidates"]), 500)
        response = self.client.get("/admin/collaborators/export.csv", headers={"X-Admin-Key": "test-api-key"})
        self.assertEqual(len(list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))), 507)

    def test_unavailable_research_store_returns_private_503(self):
        with patch.object(store, "snapshot", side_effect=OSError("private path")):
            response = self.client.get("/api/admin/collaborators", headers={"X-Admin-Key": "test-api-key"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertNotIn("private path", response.text)


if __name__ == "__main__":
    unittest.main()
