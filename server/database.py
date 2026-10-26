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
        LuluSubmission,
        ProdigiSubmission,
        SlantSubmission,
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
    if "pinterest_pins" in insp.get_table_names():
        with engine.begin() as conn:
            # Keep the audit history while counting each live Pinterest ID once.
            conn.execute(text("""UPDATE pinterest_pins SET status='duplicate'
                WHERE status='active' AND pin_id<>'' AND id NOT IN
                (SELECT min(id) FROM pinterest_pins WHERE status='active' AND pin_id<>'' GROUP BY pin_id)"""))
            conn.execute(text("""CREATE UNIQUE INDEX IF NOT EXISTS uq_active_pinterest_pin
                ON pinterest_pins(pin_id) WHERE pin_id<>'' AND status='active'"""))
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
        if "lulu_package" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN lulu_package VARCHAR(40) DEFAULT ''"))
        if "draft" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN draft BOOLEAN DEFAULT 0"))
        if "title_es" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN title_es VARCHAR(300) DEFAULT ''"))
        if "description_es" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN description_es TEXT DEFAULT ''"))
        if "etsy_listing_id" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN etsy_listing_id VARCHAR(40) DEFAULT ''"))
        if "printify_twin_id" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN printify_twin_id VARCHAR(40) DEFAULT ''"))
    if "product_variants" in insp.get_table_names():
        vcols = {c["name"] for c in insp.get_columns("product_variants")}
        if "printify_variant_id" not in vcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE product_variants ADD COLUMN printify_variant_id INTEGER DEFAULT 0"))
        if "digital_file" not in vcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE product_variants ADD COLUMN digital_file VARCHAR(200) DEFAULT ''"))
        if "print_cover" not in vcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE product_variants ADD COLUMN print_cover VARCHAR(200) DEFAULT ''"))
    # order_items.variant_id
    if "order_items" in insp.get_table_names():
        ocols = {c["name"] for c in insp.get_columns("order_items")}
        if "variant_id" not in ocols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE order_items ADD COLUMN variant_id INTEGER DEFAULT 0"))
    # orders.cart_reminder_sent_at
    if "orders" in insp.get_table_names():
        rcols = {c["name"] for c in insp.get_columns("orders")}
        if "shipping_tax_id" not in rcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN shipping_tax_id VARCHAR(80) DEFAULT ''"))
        if "cart_reminder_sent_at" not in rcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN cart_reminder_sent_at DATETIME"))
        if "printify_order_id" not in rcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN printify_order_id VARCHAR(80) DEFAULT ''"))
        if "prodigi_order_id" not in rcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN prodigi_order_id VARCHAR(120) DEFAULT ''"))
        if "lulu_job_id" not in rcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN lulu_job_id VARCHAR(80) DEFAULT ''"))
        if "slant_order_id" not in rcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN slant_order_id VARCHAR(40) DEFAULT ''"))
    if "newsletter_subscribers" in insp.get_table_names():
        ncols = {c["name"] for c in insp.get_columns("newsletter_subscribers")}
        with engine.begin() as conn:
            if "lang" not in ncols:
                conn.execute(text("ALTER TABLE newsletter_subscribers ADD COLUMN lang VARCHAR(5) DEFAULT 'en'"))
            if "welcome_step" not in ncols:
                conn.execute(text("ALTER TABLE newsletter_subscribers ADD COLUMN welcome_step INTEGER DEFAULT 0"))
            if "welcome_at" not in ncols:
                conn.execute(text("ALTER TABLE newsletter_subscribers ADD COLUMN welcome_at DATETIME"))
