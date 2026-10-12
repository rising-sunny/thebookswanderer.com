import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB = f"sqlite:///{(DATA_DIR / 'store.db').as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB)

# SQLite needs check_same_thread=False for FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from models import (  # noqa: F401
        DownloadToken,
        EmailOptOut,
        LiveEvent,
        NewsletterSubscriber,
        Order,
        OrderItem,
        PinterestPin,
        Product,
        ProductVariant,
    )
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)
    try:
        from live import _ensure_schema

        _ensure_schema()
    except Exception:
        pass

    # Lightweight migrations for SQLite (create_all won't add columns)
    if not DATABASE_URL.startswith("sqlite"):
        return
    insp = inspect(engine)
    if "products" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("products")}
    with engine.begin() as conn:
        if "gallery_json" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN gallery_json TEXT DEFAULT '[]'"))
        if "details_html" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN details_html TEXT DEFAULT ''"))
        if "video_url" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN video_url VARCHAR(500) DEFAULT ''"))
        if "video_poster" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN video_poster VARCHAR(500) DEFAULT ''"))
        if "supplier" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN supplier VARCHAR(20) DEFAULT 'cj'"))
        if "printify_product_id" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN printify_product_id VARCHAR(40) DEFAULT ''"))
        if "digital_file" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN digital_file VARCHAR(200) DEFAULT ''"))
    if "product_variants" in insp.get_table_names():
        vcols = {c["name"] for c in insp.get_columns("product_variants")}
        if "printify_variant_id" not in vcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE product_variants ADD COLUMN printify_variant_id INTEGER DEFAULT 0"))
        if "digital_file" not in vcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE product_variants ADD COLUMN digital_file VARCHAR(200) DEFAULT ''"))
    # order_items.variant_id
    if "order_items" in insp.get_table_names():
        ocols = {c["name"] for c in insp.get_columns("order_items")}
        if "variant_id" not in ocols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE order_items ADD COLUMN variant_id INTEGER DEFAULT 0"))
    # orders.cart_reminder_sent_at
    if "orders" in insp.get_table_names():
        rcols = {c["name"] for c in insp.get_columns("orders")}
        if "cart_reminder_sent_at" not in rcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN cart_reminder_sent_at DATETIME"))
        if "printify_order_id" not in rcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN printify_order_id VARCHAR(80) DEFAULT ''"))
