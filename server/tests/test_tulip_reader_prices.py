"""Tulip reader draft: prices only the 1- and 2-piece options and refuses a thin margin."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from scripts import set_tulip_reader_prices as tulip
from services import pricing

COSTS = {"1698953982217039872": 4.31, "1699031799399198720": 8.54,
         "1699031799428558848": 17.08, "1699031799453724672": 34.16}


class TulipPrices(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        models.Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.addCleanup(self.db.close)
        product = models.Product(slug=tulip.SLUG, title="x", supplier="cj", cj_pid=tulip.PID, active=False, price_usd=9.99)
        self.db.add(product)
        self.db.flush()
        for i, (vid, cost) in enumerate(COSTS.items()):
            self.db.add(models.ProductVariant(product_id=product.id, cj_vid=vid, name=f"v{i}", cost_usd=cost,
                                              price_usd=9.99, sort_order=i, active=True))
        self.db.commit()
        self.cfg = pricing.pricing_config()

    def test_keeps_two_options_with_the_new_prices_and_never_touches_active(self):
        freights = {"1698953982217039872": 4.0, "1699031799399198720": 5.0}
        report = tulip.apply_prices(self.db, freights, self.cfg)
        self.db.commit()
        variants = {v.cj_vid: v for v in self.db.query(models.ProductVariant)}
        self.assertEqual((variants["1698953982217039872"].price_usd, variants["1699031799399198720"].price_usd), (19.99, 34.99))
        self.assertEqual([v.active for v in variants.values()], [True, True, False, False])
        product = self.db.query(models.Product).one()
        self.assertEqual(product.price_usd, 19.99)
        self.assertFalse(product.active)
        self.assertEqual(len(report), 2)
        self.assertTrue(all(r["net"] >= tulip.MIN_NET_USD for r in report.values()))

    def test_refuses_when_freight_eats_the_margin_and_writes_nothing(self):
        with self.assertRaises(ValueError):
            tulip.apply_prices(self.db, {"1698953982217039872": 14.0, "1699031799399198720": 5.0}, self.cfg)
        self.db.rollback()
        self.assertEqual({v.price_usd for v in self.db.query(models.ProductVariant)}, {9.99})

    def test_net_profit_matches_the_pricing_fees(self):
        net = tulip.net_profit(19.99, 4.31, 4.0, self.cfg)
        self.assertAlmostEqual(net, 19.99 - (19.99 * 0.0349 + 0.49) - 4.31 - 0.35 - 4.0, places=2)


if __name__ == "__main__":
    unittest.main()
