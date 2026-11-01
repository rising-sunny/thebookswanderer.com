"""Run the actual subscription handler with a temporary DB and queued tasks only.
Application startup, SMTP and providers are never loaded.
"""
import ast
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks, Depends
from database import Base, get_db
from models import EmailOptOut, NewsletterSubscriber

source = Path(__file__).resolve().parents[1] / "main.py"
node = next(n for n in ast.parse(source.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == "newsletter_subscribe")
node.decorator_list = []
namespace = dict(NewsletterIn=object, BackgroundTasks=BackgroundTasks, Session=Session,
                 Depends=Depends, get_db=get_db, re=re, _send_welcome_step=Mock())
exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.tasks = BackgroundTasks()

    def request(self):
        return namespace["newsletter_subscribe"](SimpleNamespace(
            email="reader@example.invalid", lang="es", source="challenge-page"
        ), self.tasks, self.db)

    def test_new_request_is_queued_not_delivered(self):
        self.assertEqual(self.request(), dict(ok=True, already=False, email_status="queued"))
        self.assertEqual(len(self.tasks.tasks), 1)
        sub = self.db.query(NewsletterSubscriber).one()
        self.assertEqual((sub.lang, sub.source, sub.welcome_step), ("es", "challenge-page", 0))

    def test_existing_welcome_does_not_claim_another_send(self):
        self.db.add(NewsletterSubscriber(email="reader@example.invalid", welcome_step=1))
        self.db.commit()
        self.assertEqual(self.request()["email_status"], "not_queued")
        self.assertEqual(self.tasks.tasks, [])

    def test_existing_unsent_welcome_is_queued(self):
        self.db.add(NewsletterSubscriber(email="reader@example.invalid", welcome_step=0))
        self.db.commit()
        self.assertEqual(self.request()["email_status"], "queued")
        self.assertEqual(len(self.tasks.tasks), 1)

    def test_opt_out_is_preserved(self):
        self.db.add(EmailOptOut(email="reader@example.invalid"))
        self.db.commit()
        self.assertEqual(self.request()["email_status"], "not_queued")
        self.assertEqual(self.tasks.tasks, [])
        self.assertEqual(self.db.query(NewsletterSubscriber).count(), 0)

if __name__ == "__main__":
    unittest.main()
