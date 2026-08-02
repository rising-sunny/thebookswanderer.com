import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    """A sellable product (may have many CJ variants / options)."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    gallery_json: Mapped[str] = mapped_column(Text, default="[]")
    details_html: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(120), default="")

    # CJ product id (SPU level)
    cj_pid: Mapped[str] = mapped_column(String(80), index=True, default="")
    # Defaults kept for backward compat (first/active variant mirrors)
    cj_vid: Mapped[str] = mapped_column(String(80), default="")
    cj_sku: Mapped[str] = mapped_column(String(80), default="")

    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    from_country: Mapped[str] = mapped_column(String(8), default="CN")

    # Optional product demo video (self-hosted preferred over CJ hotlink)
    video_url: Mapped[str] = mapped_column(String(500), default="")
    video_poster: Mapped[str] = mapped_column(String(500), default="")

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.sort_order",
    )

    def gallery(self) -> list[str]:
        try:
            data = json.loads(self.gallery_json or "[]")
            if isinstance(data, list):
                return [str(u) for u in data if u]
        except json.JSONDecodeError:
            pass
        return [self.image_url] if self.image_url else []

    def active_variants(self) -> list["ProductVariant"]:
        return [v for v in (self.variants or []) if v.active]

    def default_variant(self) -> "ProductVariant | None":
        act = self.active_variants()
        return act[0] if act else None

    def to_public(self) -> dict:
        from services import categories as cat_service

        variants = self.active_variants()
        prices = [v.price_usd for v in variants] or [self.price_usd]
        # Prefer product hero image when set; else first variant
        img = self.image_url
        if not img and variants and variants[0].image_url:
            img = variants[0].image_url
        cat_meta = cat_service.public_meta(self.category)
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "image_url": img,
            "category": cat_meta["category"],
            "category_slug": cat_meta["category_slug"],
            "price_usd": round(min(prices), 2),
            "price_max_usd": round(max(prices), 2),
            "from_country": self.from_country,
            "variant_count": len(variants),
            "has_variants": len(variants) > 1,
        }

    def to_detail(self) -> dict:
        variants = self.active_variants()
        # Lifestyle / ambient pack shots (not the design picker thumbs)
        lifestyle = self.gallery()
        variant_imgs = {v.image_url for v in variants if v.image_url}
        lifestyle = [u for u in lifestyle if u and u not in variant_imgs]

        return {
            **self.to_public(),
            "images": lifestyle,  # kept for compatibility
            "lifestyle_images": lifestyle,
            "details_html": self.details_html or "",
            "cj_sku": self.cj_sku,
            "video_url": self.video_url or "",
            "video_poster": self.video_poster or "",
            "variants": [v.to_public() for v in variants],
            "default_variant_id": variants[0].id if variants else None,
        }


class ProductVariant(Base):
    """A selectable option of a product (color/design), mapped to a CJ vid."""

    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")  # e.g. design name
    cj_vid: Mapped[str] = mapped_column(String(80), index=True, default="")
    cj_sku: Mapped[str] = mapped_column(String(80), default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped["Product"] = relationship(back_populates="variants")

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "image_url": self.image_url,
            "price_usd": round(self.price_usd, 2),
            "cj_sku": self.cj_sku,
            "cj_vid": self.cj_vid,
        }


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")

    email: Mapped[str] = mapped_column(String(200), default="")
    customer_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")

    shipping_address: Mapped[str] = mapped_column(String(300), default="")
    shipping_address2: Mapped[str] = mapped_column(String(300), default="")
    shipping_city: Mapped[str] = mapped_column(String(120), default="")
    shipping_province: Mapped[str] = mapped_column(String(120), default="")
    shipping_zip: Mapped[str] = mapped_column(String(40), default="")
    shipping_country: Mapped[str] = mapped_column(String(80), default="")
    shipping_country_code: Mapped[str] = mapped_column(String(8), default="")

    product_total: Mapped[float] = mapped_column(Float, default=0.0)
    shipping_total: Mapped[float] = mapped_column(Float, default=0.0)
    grand_total: Mapped[float] = mapped_column(Float, default=0.0)

    logistic_name: Mapped[str] = mapped_column(String(120), default="")
    shipping_eta: Mapped[str] = mapped_column(String(40), default="")

    paypal_order_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    cj_order_id: Mapped[str] = mapped_column(String(80), default="")
    cj_order_number: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    # Abandoned-checkout reminder: set once so nobody is emailed twice.
    # See server/scripts/send_cart_reminders.py
    cart_reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(Integer, default=0)
    variant_id: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    cj_vid: Mapped[str] = mapped_column(String(80), default="")
    cj_sku: Mapped[str] = mapped_column(String(80), default="")

    order: Mapped["Order"] = relationship(back_populates="items")


class LiveEvent(Base):
    """Self-hosted analytics event for /admin/live dashboard."""

    __tablename__ = "live_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    referrer_domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ua_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    product_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    value_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    medium: Mapped[str | None] = mapped_column(String(40), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)


class EmailOptOut(Base):
    """Quien pidió no recibir más recordatorios.

    El envío de recordatorios de carrito se ampara en el soft opt-in del PECR
    británico y equivalentes europeos, que exige una salida fácil en cada
    mensaje. Cada email lleva un enlace firmado a /api/unsubscribe, y esta
    tabla es la lista de supresión que consulta el script antes de enviar.
    """

    __tablename__ = "email_opt_outs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    source: Mapped[str] = mapped_column(String(40), default="unsubscribe_link")


class NewsletterSubscriber(Base):
    """Suscriptor del boletín.

    Existe porque el formulario de la portada decía "You're in! Check your
    inbox" y tiraba la dirección: no había backend, ni lista, ni confirmación
    que revisar. Ahora la dirección se guarda de verdad.
    """

    __tablename__ = "newsletter_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    source: Mapped[str] = mapped_column(String(40), default="homepage")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
