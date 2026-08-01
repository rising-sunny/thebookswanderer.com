"""Simulate a paid order and send confirmation email (or write HTML preview)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import email as email_service  # noqa: E402
from services.email import (  # noqa: E402
    _esc,
    _money,
    _order_address,
    _order_lines_html,
    _wrap_html,
)


def build_demo():
    order = SimpleNamespace(
        id=9001,
        email="esteban.hopestarstore@gmail.com",
        customer_name="Esteban",
        product_total=19.98,
        shipping_total=4.50,
        grand_total=24.48,
        shipping_address="123 Reading Lane",
        shipping_address2="Apt 4",
        shipping_city="Santiago",
        shipping_province="RM",
        shipping_zip="8320000",
        shipping_country="Chile",
        shipping_country_code="CL",
        phone="+56900000000",
        cj_order_number="TBW-9001",
    )
    items = [
        SimpleNamespace(
            title='Kindle Magnetic Sleeve — Pink · 6"',
            quantity=2,
            unit_price=9.99,
        ),
        SimpleNamespace(
            title="Hollow Kitten Bookmark — Single",
            quantity=1,
            unit_price=7.99,
        ),
    ]
    return order, items


def write_preview(order, items, path: Path) -> None:
    """Local HTML preview using the same branded shell as live emails."""
    oid = order.id
    name = order.customer_name
    base = email_service._public_base()
    html = _wrap_html(
        preheader=f"Payment received for order #{oid}",
        eyebrow="Order confirmation",
        body_html=f"""
          <h1 style="margin:0 0 10px;font-family:Georgia,serif;font-size:24px;font-weight:600;
                     color:#1b3728;line-height:1.25">Order confirmed</h1>
          <p style="margin:0 0 18px;font-size:15px;line-height:1.6;color:#333">
            Hi {_esc(name)}, thank you for wandering into our shop.
            We received your payment for <strong style="color:#1b3728">order #{_esc(oid)}</strong>.
          </p>
          <p style="margin:0 0 14px;font-family:Arial,sans-serif;font-size:12px;color:#a08b4a">
            <em>Simulated purchase (test) — not a real PayPal charge.</em>
          </p>
          <p style="margin:0 0 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                     letter-spacing:0.12em;text-transform:uppercase;color:#a08b4a">Your pieces</p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                 style="margin:0 0 18px">{_order_lines_html(items)}</table>
          <table role="presentation" width="100%" style="margin:0 0 18px;font-family:Arial,Helvetica,sans-serif;font-size:14px">
            <tr>
              <td style="padding:4px 0;color:#6b5c3e">Subtotal</td>
              <td style="padding:4px 0;text-align:right;color:#1b3728">{_esc(_money(order.product_total))}</td>
            </tr>
            <tr>
              <td style="padding:4px 0;color:#6b5c3e">Shipping</td>
              <td style="padding:4px 0;text-align:right;color:#1b3728">{_esc(_money(order.shipping_total))}</td>
            </tr>
            <tr>
              <td style="padding:10px 0 0;border-top:1px solid #e8dfc8;font-weight:700;color:#1b3728">Total paid</td>
              <td style="padding:10px 0 0;border-top:1px solid #e8dfc8;text-align:right;font-weight:700;color:#1b3728;font-size:16px">{_esc(_money(order.grand_total))}</td>
            </tr>
          </table>
          <p style="margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                     letter-spacing:0.12em;text-transform:uppercase;color:#a08b4a">Ship to</p>
          <p style="margin:0 0 20px;font-size:14px;line-height:1.55;color:#444;white-space:pre-line">{_esc(_order_address(order))}</p>
          <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:#555">
            We’ll write again when your package is on its way.
          </p>
          <p style="margin:0;text-align:center">
            <a href="{_esc(base)}" style="display:inline-block;padding:12px 22px;background:#2b5240;color:#f8f2e5;
               text-decoration:none;border-radius:999px;font-family:Arial,Helvetica,sans-serif;
               font-size:14px;font-weight:700">Visit the shop</a>
          </p>
        """,
    )
    path.write_text(html, encoding="utf-8")
    print("preview_written", path, path.stat().st_size)


async def main() -> None:
    order, items = build_demo()
    to = sys.argv[1] if len(sys.argv) > 1 else order.email
    order.email = to

    preview = ROOT / "data" / "order_confirm_preview.html"
    preview.parent.mkdir(parents=True, exist_ok=True)
    write_preview(order, items, preview)

    print("smtp_configured", email_service.configured())
    if not email_service.configured():
        print(
            "SEND_SKIPPED: SMTP not configured. "
            "Set SMTP_* and MAIL_FROM in server/.env, restart thebookswanderer, re-run."
        )
        return

    ok = await email_service.send_order_paid(order, items)
    print("send_ok", ok, "to", to)


if __name__ == "__main__":
    asyncio.run(main())
