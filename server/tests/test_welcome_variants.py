"""The welcome series depends on where the person signed up (the page's `source`)."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import email as E


class WelcomeVariantTests(unittest.TestCase):
    def send(self, step, lang, source):
        sent = {}

        async def fake(**kw):
            sent.update(kw)
            return True

        old = E.send_email
        E.send_email = fake
        try:
            asyncio.run(E.send_welcome(step, "reader@example.invalid", lang, "https://example.invalid/u", source))
        finally:
            E.send_email = old
        return sent

    def test_austen_sources_get_the_austen_plan_in_each_language(self):
        for src in ("austen-guide-netflix", "austen-guide-netflix-es"):
            en = self.send(1, "en", src)
            self.assertIn("/assets/downloads/jane-austen-reading-plan-2027.pdf", en["text"])
            self.assertIn("Jane Austen reading plan", en["subject"])
            es = self.send(1, "es", src)
            self.assertIn("/assets/downloads/plan-de-lectura-jane-austen-2027.pdf", es["text"])
        two = self.send(2, "en", "austen-guide-netflix")
        self.assertIn("/products/pride-and-prejudice-watch-party-kit", two["text"])
        self.assertIn("/products/jane-austen-puzzle-book", two["text"])
        self.assertIn("/es/products/jane-austen-puzzle-book", self.send(2, "es", "austen-guide-netflix-es")["text"])

    def test_step_three_for_austen_falls_back_to_the_common_gift_letter(self):
        self.assertEqual(self.send(3, "en", "austen-guide-netflix")["subject"], self.send(3, "en", "challenge-page")["subject"])

    def test_other_sources_are_unchanged(self):
        self.assertIn("/assets/downloads/2027-reading-challenge.pdf", self.send(1, "en", "challenge-page")["text"])
        self.assertIn("/assets/downloads/2027-reading-challenge.pdf", self.send(1, "en", "guide-ideas-2027")["text"])
        self.assertIn("free-literary-coloring-pages.pdf", self.send(1, "en", "coloring-page")["text"])


if __name__ == "__main__":
    unittest.main()
