
"""Exercise the actual snapshot query against an in-memory fixture database.
Only the relevant AST definitions are loaded: the application is never imported.
"""
import ast
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine, func
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
    if isinstance(node, ast.FunctionDef) and node.name == "_build_snapshot"
    or isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "VALID_EVENTS" for t in node.targets)
]
namespace = {
    "datetime": datetime, "timedelta": timedelta, "Session": Session,
    "LiveEvent": Event, "func": func,
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

    def add(self, kind, seconds, session="fixture", value=19.99):
        self.db.add(Event(
            ts=self.now - timedelta(seconds=seconds), session_id=session,
            event_type=kind, ua_class="mobile", value_usd=value,
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

    def test_purchase_still_closes_funnel(self):
        self.add("add_to_cart", 30)
        self.add("purchase", 20)
        self.add("cart_load_error", 10)
        result = self.snapshot()
        self.assertEqual(result["active_carts"], 0)
        self.assertEqual(result["active_checkouts"], 0)
        self.assertEqual(result["today"]["purchases"], 1)

    def test_opening_alone_does_not_create_active_cart(self):
        self.add("cart_open", 10)
        self.assertEqual(self.snapshot()["active_carts"], 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
