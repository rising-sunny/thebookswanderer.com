
"""Exercise the actual snapshot query against an in-memory fixture database.
Only the relevant AST definitions are loaded: the application is never imported.
"""
import ast
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine, func, case
from sqlalchemy.orm import Session, declarative_base

Base = declarative_base()

class Event(Base):
    __tablename__ = "fixture_events"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime)
    session_id = Column(String)
    event_type = Column(String)
    ua_class = Column(String)
    value_usd = Column(Float)
    path = Column(String)
    source = Column(String)
    referrer_domain = Column(String)
    medium = Column(String)
    campaign = Column(String)
    country = Column(String)
    country_name = Column(String)
    product_slug = Column(String)
    city = Column(String)

path = Path(__file__).resolve().parents[1] / "live.py"
tree = ast.parse(path.read_text())
nodes = [
    node for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name in ("_build_snapshot", "_history_payload", "_confirmed_purchase")
    or isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "VALID_EVENTS" for t in node.targets)
]
namespace = {
    "datetime": datetime, "timedelta": timedelta, "Session": Session,
    "LiveEvent": Event, "func": func, "case": case,
    "ACTIVE_VISITOR_WINDOW": 300, "ACTIVE_FUNNEL_WINDOW": 1800,
    "_NOT_HUMAN": ("server", "datacenter"),
    "_norm_path": lambda: Event.path,
    "_normalize_source": lambda *args: ("Fixture", ""),
    "_flag": lambda code: "",
}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)

class CartDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.now = datetime.utcnow()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add(self, kind, seconds, session="fixture", value=19.99, ua="mobile"):
        self.db.add(Event(
            ts=self.now - timedelta(seconds=seconds), session_id=session,
            event_type=kind, ua_class=ua, value_usd=value,
            path="/fixture", product_slug="fixture-book",
        ))
        self.db.commit()

    def snapshot(self):
        return namespace["_build_snapshot"](self.db)

    def test_event_allowlist(self):
        self.assertTrue(
            {"cart_open", "cart_load_error", "cart_view", "purchase"}
            <= namespace["VALID_EVENTS"]
        )

    def test_diagnostics_preserve_cart(self):
        self.add("add_to_cart", 30)
        self.add("cart_open", 20)
        self.add("cart_load_error", 10)
        result = self.snapshot()
        self.assertEqual(result["active_carts"], 1)
        self.assertEqual(result["carts_value"], 19.99)

    def test_diagnostics_preserve_checkout(self):
        self.add("checkout_start", 30)
        self.add("cart_load_error", 10)
        result = self.snapshot()
        self.assertEqual(result["active_checkouts"], 1)
        self.assertEqual(result["active_carts"], 0)

    def test_equal_timestamp_does_not_duplicate_cart(self):
        self.add("add_to_cart", 20)
        self.add("cart_open", 20)
        self.assertEqual(self.snapshot()["active_carts"], 1)

    def test_legacy_browser_purchase_closes_funnel_without_confirming_sale(self):
        self.add("add_to_cart", 30)
        self.add("purchase", 20)
        self.add("cart_load_error", 10)
        result = self.snapshot()
        self.assertEqual(result["active_carts"], 0)
        self.assertEqual(result["active_checkouts"], 0)
        self.assertEqual(result["today"]["purchases"], 0)

    def test_server_sale_and_repeated_returns_count_once_everywhere(self):
        self.add("purchase", 60, session="srv_paypal_1", value=25, ua="server")
        self.add("purchase", 50, value=25)  # Legacy browser row, before this change.
        self.add("purchase_return", 40, value=25)
        self.add("purchase_return", 30, value=25)
        self.assertEqual(self.snapshot()["today"]["purchases"], 1)
        self.assertEqual(self.snapshot()["today"]["revenue"], 25)
        history = namespace["_history_payload"](self.db, 7)
        self.assertEqual(history["current"]["purchases"], 1)
        self.assertEqual(history["current"]["revenue"], 25)
        self.assertEqual(sum(d["purchases"] for d in history["daily"]), 1)
        self.assertEqual(sum(d["revenue"] for d in history["daily"]), 25)
        self.assertEqual(history["top_products"][0]["sales"], 1)
        self.assertEqual(history["top_products"][0]["revenue"], 25)

    def test_return_closes_checkout_without_confirming_sale(self):
        self.add("checkout_start", 40)
        self.add("purchase_return", 30)
        self.assertEqual(self.snapshot()["active_checkouts"], 0)
        self.assertEqual(self.snapshot()["today"]["purchases"], 0)

    def test_challenge_events_do_not_erase_cart_or_checkout(self):
        self.add("add_to_cart", 40, session="cart-fixture")
        self.add("challenge_product_click", 30, session="cart-fixture")
        self.add("checkout_start", 40, session="checkout-fixture")
        self.add("challenge_request", 30, session="checkout-fixture")
        self.assertEqual(self.snapshot()["active_carts"], 1)
        self.assertEqual(self.snapshot()["active_checkouts"], 1)

    def test_opening_alone_does_not_create_active_cart(self):
        self.add("cart_open", 10)
        self.assertEqual(self.snapshot()["active_carts"], 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
