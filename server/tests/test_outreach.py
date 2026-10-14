"""Offline tests for once-only sending, suppression and autonomous discovery."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from services import outreach
from services import collaborators_store as store
from services.invitation import draft, SENDER
from routers.outreach import router
from database import Base
from models import EmailOptOut, NewsletterSubscriber
import discover_literary_sources as discovery


class OutreachTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"COLLABORATORS_DATA_DIR": folder.name, "SECRET_KEY": "test-key", "MAIL_FROM": "orders@thebookswanderer.com", "SMTP_HOST": "smtp.test", "SMTP_USER": "test", "SMTP_PASSWORD": "test-password", "SMTP_PORT": "465", "SMTP_SSL": "1"})
        env.start(); self.addCleanup(env.stop)
        store.init_store()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine)
        sessions = patch("database.SessionLocal", self.sessions)
        sessions.start();self.addCleanup(sessions.stop)
        with store.connect() as db:
            sid = db.execute("INSERT INTO sources(name,url,lang,category,reason) VALUES('Book Blog','https://bookblog.org/','en','Blog','Book reviews')").lastrowid
            for address in ("contact@bookblog.org", "bookblog@gmail.com"):
                store.save_candidate(db, sid, {"email": address, "source_url": "https://bookblog.org/contact", "evidence": "Contact for collaborations", "purpose": "Colaboraciones / publicidad"})
        app = FastAPI(); app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_preview_and_sent_message_share_approved_copy(self):
        content = draft("es", "https://thebookswanderer.com/api/outreach/unsubscribe?test=1")
        self.assertIn("Te invitamos a The Books Wanderer", content["subject"])
        self.assertIn("52 propuestas", content["text"])
        self.assertIn("#newsletter", content["html"])
        self.assertIn("No recibir más invitaciones", content["html"])

    def test_automatic_selection_uses_one_professional_address_per_site(self):
        self.assertEqual(outreach.auto_candidates(), [1])
        with store.connect() as db:
            db.execute("UPDATE candidates SET status='discarded' WHERE id=1")
        self.assertEqual(outreach.auto_candidates(), [2])

    def test_suppression_and_existing_subscription_prevent_sending(self):
        with self.sessions() as db:
            db.add(EmailOptOut(email="contact@bookblog.org")); db.commit()
        rows = outreach.selected_candidates([1])
        outreach.prepare("test-campaign", rows)
        with patch.object(outreach.mail, "_send_sync") as send:
            totals = outreach.deliver("test-campaign", pause_seconds=0)
            send.assert_not_called()
        self.assertEqual(totals, {"suppressed": 1})
        with self.sessions() as db:
            db.add(NewsletterSubscriber(email="bookblog@gmail.com", active=True)); db.commit()
        self.assertEqual(outreach.global_contact_state("bookblog@gmail.com"), "already_subscribed")

    def test_repeated_campaign_and_new_campaign_label_never_resend(self):
        rows = outreach.selected_candidates([1])
        self.assertEqual(outreach.prepare("first-campaign", rows), 1)
        with patch.object(outreach.mail, "_send_sync", return_value=True) as send:
            self.assertEqual(outreach.deliver("first-campaign", 0), {"sent": 1})
            self.assertEqual(outreach.prepare("first-campaign", rows), 0)
            self.assertEqual(outreach.prepare("second-campaign", outreach.selected_candidates([2])), 0)
            outreach.deliver("first-campaign", 0)
            self.assertEqual(send.call_count, 1)
            args = send.call_args.kwargs
            self.assertEqual(args["to"], ["contact@bookblog.org"])
            self.assertEqual(args["from_address"], SENDER)
            self.assertEqual(args["reply_to"], SENDER)
            self.assertIn("List-Unsubscribe", args["headers"])
            self.assertIn(args["message_id"], [r[0] for r in self._query("SELECT message_id FROM outreach_deliveries")])
        self.assertEqual(store.snapshot()["counts"]["contacted"], 1)

    def _query(self, sql):
        with store.connect() as db:return db.execute(sql).fetchall()

    def test_ambiguous_smtp_result_is_not_retried(self):
        rows = outreach.selected_candidates([1]);outreach.prepare("test-campaign", rows)
        with patch.object(outreach.mail, "_send_sync", return_value=False) as send:
            self.assertEqual(outreach.deliver("test-campaign", 0), {"uncertain": 1})
            outreach.deliver("test-campaign", 0)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(store.snapshot()["counts"]["contacted"], 0)

    def test_pause_or_discard_between_queue_and_delivery_prevents_send(self):
        outreach.prepare("test-campaign", outreach.selected_candidates([1]))
        with store.connect() as db:db.execute("UPDATE sources SET active=0")
        with patch.object(outreach.mail, "_send_sync") as send:
            self.assertEqual(outreach.deliver("test-campaign", 0), {"suppressed": 1})
            send.assert_not_called()

    def test_one_click_optout_is_signed_and_get_does_not_mutate(self):
        email="contact@bookblog.org";token=outreach.unsubscribe_token(email)
        params={"email":email,"t":token,"lang":"en"}
        self.assertEqual(self.client.get("/api/outreach/unsubscribe",params=params).status_code,200)
        self.assertFalse(outreach.locally_suppressed(email))
        self.assertEqual(self.client.post("/api/outreach/unsubscribe",params=params,data={"List-Unsubscribe":"One-Click"}).status_code,200)
        self.assertTrue(outreach.locally_suppressed(email))
        self.assertEqual(outreach.global_contact_state(email),"opted_out")
        self.assertEqual(self.client.post("/api/outreach/unsubscribe",params=params).status_code,200)
        params["t"]="0"*32
        self.assertEqual(self.client.post("/api/outreach/unsubscribe",params=params).status_code,400)

    def test_ten_attempts_per_rolling_day_limit(self):
        rows=outreach.selected_candidates([1]);outreach.prepare("test-campaign",rows)
        with store.connect() as db:
            for i in range(10):
                sid=db.execute("INSERT INTO sources(name,url,lang,category,reason) VALUES(?,?,?,?,?)",(f"Blog {i}",f"https://blog{i}.org/","en","Blog","Reviews")).lastrowid
                store.save_candidate(db,sid,{"email":f"hello@blog{i}.org","source_url":f"https://blog{i}.org/contact","evidence":"Professional contact","purpose":"Contact"})
                cid=db.execute("SELECT id FROM candidates WHERE source_id=?",(sid,)).fetchone()[0]
                db.execute("INSERT INTO outreach_deliveries(campaign_id,candidate_id,source_id,site_key,email,lang,subject,html,text,message_id,status,created_at,attempted_at) VALUES(?,?,?,?,?,'en','subject','html','text',?,'sent',?,?)",("test-campaign",cid,sid,f"blog{i}.org",f"hello@blog{i}.org",f"<{i}@test>",store.now(),store.now()))
        with patch.object(outreach.mail,"_send_sync") as send:
            outreach.deliver("test-campaign",0);send.assert_not_called()

    def test_dry_run_does_not_approve_queue_or_send(self):
        with patch.object(outreach,"smtp_preflight",return_value={"sender":SENDER}),patch.object(outreach.mail,"_send_sync") as send:
            result=outreach.run("test-campaign",[1],False)
            self.assertEqual(result["eligible"],1);send.assert_not_called()
        self.assertEqual(store.snapshot()["counts"]["pending"],2)
        self.assertEqual(store.snapshot()["deliveries"],[])

    def test_smtp_preflight_checks_hello_envelope_without_sending(self):
        connection=MagicMock();server=connection.__enter__.return_value;server.mail.return_value=(250,b"OK")
        with patch.object(outreach.smtplib,"SMTP_SSL",return_value=connection):
            self.assertEqual(outreach.smtp_preflight()["sender"],SENDER)
        server.mail.assert_called_once_with(SENDER)
        server.rset.assert_called_once();server.sendmail.assert_not_called();server.send_message.assert_not_called()

    def test_plaintext_smtp_is_rejected_before_credentials_are_used(self):
        with patch.dict(os.environ,{"SMTP_PORT":"587","SMTP_SSL":"0","SMTP_STARTTLS":"0"}),patch.object(outreach.smtplib,"SMTP") as connect:
            with self.assertRaises(ValueError):outreach.smtp_preflight()
            connect.assert_not_called()

    def test_requested_sample_uses_exact_invitation_once_without_adding_a_lead(self):
        before = store.snapshot()
        with patch.object(outreach,"smtp_preflight"),patch.object(outreach.mail,"_send_sync",return_value=True) as send:
            self.assertEqual(outreach.send_sample("owner@example.org","es","sample-request-1")["status"],"sent")
            self.assertEqual(outreach.send_sample("owner@example.org","es","sample-request-1")["status"],"already_sent")
            self.assertEqual(send.call_count,1)
            args=send.call_args.kwargs
            self.assertEqual(args["to"],["owner@example.org"])
            self.assertEqual(args["from_address"],SENDER)
            self.assertEqual(args["reply_to"],SENDER)
            self.assertEqual(args["subject"],draft("es")["subject"])
            self.assertIn("store_invitation_test",args["html"])
            self.assertIn("tbw_test=1",args["text"])
            self.assertNotIn("tbw_test",draft("es")["html"])
            self.assertIn("List-Unsubscribe",args["headers"])
            with self.assertRaises(ValueError):outreach.send_sample("other@example.org","es","sample-request-1")
        self.assertEqual(store.snapshot(),before)

    def test_uncertain_sample_is_not_automatically_retried(self):
        with patch.object(outreach,"smtp_preflight"),patch.object(outreach.mail,"_send_sync",return_value=False) as send:
            self.assertEqual(outreach.send_sample("owner@example.org","es","sample-request-2")["status"],"uncertain")
            self.assertEqual(outreach.send_sample("owner@example.org","es","sample-request-2")["status"],"uncertain")
            self.assertEqual(send.call_count,1)


class DiscoveryTests(unittest.TestCase):
    def test_only_relevant_external_sites_are_candidates(self):
        html='<a href="https://anotherbookblog.org/post">Book reviews</a><a href="https://facebook.com/books">Books</a><a href="http://127.0.0.1">Books</a><a href="/contact">Contact</a>'
        self.assertEqual(discovery.candidate_links(html,"https://knownbooks.org/"),["https://anotherbookblog.org/"])

    def test_topic_language_and_noindex_filters(self):
        es=discovery.literary_profile('<p>Blog de libros y lectura, reseñas de novelas, autores y literatura</p>')
        en=discovery.literary_profile('<p>Book blog, reading and readers, reviews of novels by authors</p>')
        self.assertEqual(es["lang"],"es");self.assertEqual(en["lang"],"en")
        self.assertIsNone(discovery.literary_profile('<p>Blog about cars, engines and driving</p>'))
        self.assertIsNone(discovery.literary_profile('<meta name="robots" content="noindex"><p>Book blog reading readers reviews novels</p>'))


if __name__ == "__main__":unittest.main()
