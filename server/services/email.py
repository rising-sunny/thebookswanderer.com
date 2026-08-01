"""
Transactional email via SMTP.

Configure in server/.env (see .env.example). When SMTP is not configured,
send_* functions log and no-op (checkout never fails because of email).

Typical providers:
  - Resend / SendGrid / Mailgun / Amazon SES → SMTP credentials
  - Google Workspace → app password + smtp.gmail.com:587
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Iterable

log = logging.getLogger("tbw.email")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def configured() -> bool:
    return bool(_env("SMTP_HOST") and _env("MAIL_FROM") and _env("SMTP_USER"))


def _public_base() -> str:
    return _env("PUBLIC_BASE_URL", "https://thebookswanderer.com").rstrip("/")


def _shop_name() -> str:
    return _env("MAIL_SHOP_NAME", "The Books Wanderer")


def _from_header() -> str:
    addr = _env("MAIL_FROM")
    name = _env("MAIL_FROM_NAME", _shop_name())
    return formataddr((name, addr)) if name else addr


def _notify_owner() -> list[str]:
    raw = _env("MAIL_NOTIFY_TO") or _env("MAIL_FROM")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _money(n: Any) -> str:
    try:
        return f"${float(n):.2f} USD"
    except (TypeError, ValueError):
        return "—"


def _send_sync(
    *,
    to: Iterable[str],
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
) -> bool:
    if not configured():
        log.info("email skipped (SMTP not configured): %s → %s", subject, list(to))
        return False

    recipients = [t.strip() for t in to if t and str(t).strip()]
    if not recipients:
        return False

    host = _env("SMTP_HOST")
    port = int(_env("SMTP_PORT", "587") or "587")
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    use_ssl = _env("SMTP_SSL", "").lower() in ("1", "true", "yes")
    use_starttls = _env("SMTP_STARTTLS", "1").lower() not in ("0", "false", "no")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _from_header()
    msg["To"] = ", ".join(recipients)
    msg["Message-ID"] = make_msgid(domain=_env("MAIL_FROM").split("@")[-1] or "thebookswanderer.com")
    if reply_to or _env("MAIL_REPLY_TO"):
        msg["Reply-To"] = reply_to or _env("MAIL_REPLY_TO")

    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        if use_ssl or port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=45) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=45) as smtp:
                smtp.ehlo()
                if use_starttls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        log.info("email sent: %s → %s", subject, recipients)
        return True
    except Exception:
        log.exception("email failed: %s → %s", subject, recipients)
        return False


async def send_email(
    *,
    to: Iterable[str] | str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
) -> bool:
    if isinstance(to, str):
        to = [to]
    return await asyncio.to_thread(
        _send_sync, to=to, subject=subject, text=text, html=html, reply_to=reply_to
    )


# ── Order helpers ─────────────────────────────────────────────────────


def _order_lines_text(items: list[Any]) -> str:
    lines = []
    for it in items:
        title = getattr(it, "title", None) or "Item"
        qty = getattr(it, "quantity", 1)
        unit = getattr(it, "unit_price", 0)
        lines.append(f"  • {title}  ×{qty}  {_money(unit)}")
    return "\n".join(lines) if lines else "  (no line items)"


def _order_lines_html(items: list[Any]) -> str:
    rows = []
    for it in items:
        title = getattr(it, "title", None) or "Item"
        qty = getattr(it, "quantity", 1)
        unit = getattr(it, "unit_price", 0)
        line_total = float(unit or 0) * int(qty or 1)
        rows.append(
            "<tr>"
            f"<td style='padding:14px 8px 14px 0;border-bottom:1px solid #e8dfc8;"
            f"font-family:Georgia,Times,serif;font-size:15px;color:#1b3728;line-height:1.4'>"
            f"{_esc(title)}</td>"
            f"<td style='padding:14px 8px;border-bottom:1px solid #e8dfc8;text-align:center;"
            f"font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#6b5c3e'>"
            f"×{int(qty)}</td>"
            f"<td style='padding:14px 0 14px 8px;border-bottom:1px solid #e8dfc8;text-align:right;"
            f"font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:700;color:#1b3728'>"
            f"{_money(line_total)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _esc(s: Any) -> str:
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _logo_url() -> str:
    # Lightweight brand mark for inboxes (full logo is ~1.3MB)
    return f"{_public_base()}/assets/logo-email.png"


def _btn(href: str, label: str) -> str:
    return (
        f'<a href="{_esc(href)}" '
        f'style="display:inline-block;padding:12px 22px;background:#2b5240;color:#f8f2e5;'
        f"text-decoration:none;border-radius:999px;font-family:Arial,Helvetica,sans-serif;"
        f'font-size:14px;font-weight:700;letter-spacing:0.02em">{_esc(label)}</a>'
    )


def _wrap_html(*, preheader: str, body_html: str, eyebrow: str = "") -> str:
    """
    Branded HTML shell matching thebookswanderer.com:
    cream paper, deep green, gold accents, circular logo, editorial tone.
    """
    shop = _esc(_shop_name())
    base = _esc(_public_base())
    logo = _esc(_logo_url())
    eye = _esc(eyebrow) if eyebrow else "Literary boutique"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{shop}</title>
</head>
<body style="margin:0;padding:0;background:#f0e9d8;color:#1a1a1a">
  <span style="display:none!important;visibility:hidden;opacity:0;height:0;width:0;overflow:hidden">
    {_esc(preheader)}
  </span>
  <!-- full-bleed cream -->
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="background:#f0e9d8;background-image:linear-gradient(180deg,#f8f2e5 0%,#efe6d0 100%);
                padding:32px 12px 40px;margin:0">
    <tr>
      <td align="center">
        <!-- card -->
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="max-width:560px;background:#fffdf8;border:1px solid #e0d4b8;
                      border-radius:16px;overflow:hidden;
                      box-shadow:0 8px 28px rgba(27,55,40,0.08)">
          <!-- top gold line -->
          <tr>
            <td style="height:4px;background:linear-gradient(90deg,#c1912f,#e8c56a,#c1912f);
                       font-size:0;line-height:0">&nbsp;</td>
          </tr>
          <!-- header brand -->
          <tr>
            <td align="center" style="padding:28px 28px 8px;background:#fffdf8">
              <a href="{base}" style="text-decoration:none">
                <img src="{logo}" width="88" height="88" alt="{shop}"
                     style="display:block;margin:0 auto 14px;border:0;border-radius:50%;
                            border:2px solid #e8dfc8;background:#f8f2e5">
              </a>
              <p style="margin:0;font-family:Georgia,'Times New Roman',Times,serif;
                         font-size:22px;font-weight:600;color:#1b3728;letter-spacing:0.01em">
                {shop}
              </p>
              <p style="margin:6px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                         letter-spacing:0.16em;text-transform:uppercase;color:#a08b4a">
                {eye}
              </p>
            </td>
          </tr>
          <!-- soft divider -->
          <tr>
            <td style="padding:16px 36px 8px">
              <div style="height:1px;background:#e8dfc8;font-size:0;line-height:0">&nbsp;</div>
            </td>
          </tr>
          <!-- body -->
          <tr>
            <td style="padding:12px 32px 8px;font-family:Georgia,'Times New Roman',Times,serif;
                       font-size:15px;line-height:1.6;color:#2a2a2a">
              {body_html}
            </td>
          </tr>
          <!-- footer -->
          <tr>
            <td style="padding:24px 32px 28px;background:#f8f2e5;border-top:1px solid #e8dfc8">
              <p style="margin:0 0 8px;font-family:Georgia,serif;font-size:14px;font-style:italic;
                         color:#5c6b58;text-align:center">
                “For those who wander between pages.”
              </p>
              <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:12px;
                         color:#8a7a5c;text-align:center;line-height:1.55">
                <a href="{base}" style="color:#2b5240;text-decoration:none;font-weight:600">{base}</a><br>
                Questions? Just reply to this email.<br>
                <span style="color:#b0a080">Secure checkout with PayPal</span>
              </p>
            </td>
          </tr>
        </table>
        <p style="margin:16px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                   color:#a89878;text-align:center">
          You’re receiving this because you placed an order or asked us to write.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _order_address(order: Any) -> str:
    parts = [
        getattr(order, "customer_name", "") or "",
        getattr(order, "shipping_address", "") or "",
        getattr(order, "shipping_address2", "") or "",
        ", ".join(
            p
            for p in (
                getattr(order, "shipping_city", "") or "",
                getattr(order, "shipping_province", "") or "",
                getattr(order, "shipping_zip", "") or "",
            )
            if p
        ),
        getattr(order, "shipping_country", "") or "",
    ]
    return "\n".join(p for p in parts if p)


async def send_order_paid(order: Any, items: list[Any]) -> bool:
    """Customer: payment received / order confirmation."""
    oid = getattr(order, "id", "?")
    email = getattr(order, "email", "") or ""
    name = getattr(order, "customer_name", "") or "there"
    shop = _shop_name()
    base = _public_base()

    subject = f"Order #{oid} confirmed — {shop}"
    text = f"""Hi {name},

Thank you for your order from {shop}.

We've received your payment for order #{oid}.

Items:
{_order_lines_text(items)}

Subtotal: {_money(getattr(order, "product_total", 0))}
Shipping: {_money(getattr(order, "shipping_total", 0))}
Total: {_money(getattr(order, "grand_total", 0))}

Ship to:
{_order_address(order)}

We'll email you again when your package is on its way.

— {shop}
{base}
"""
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
          <p style="margin:0 0 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                     letter-spacing:0.12em;text-transform:uppercase;color:#a08b4a">Your pieces</p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                 style="margin:0 0 18px">{_order_lines_html(items)}</table>
          <table role="presentation" width="100%" style="margin:0 0 18px;font-family:Arial,Helvetica,sans-serif;font-size:14px">
            <tr>
              <td style="padding:4px 0;color:#6b5c3e">Subtotal</td>
              <td style="padding:4px 0;text-align:right;color:#1b3728">{_esc(_money(getattr(order, "product_total", 0)))}</td>
            </tr>
            <tr>
              <td style="padding:4px 0;color:#6b5c3e">Shipping</td>
              <td style="padding:4px 0;text-align:right;color:#1b3728">{_esc(_money(getattr(order, "shipping_total", 0)))}</td>
            </tr>
            <tr>
              <td style="padding:10px 0 0;border-top:1px solid #e8dfc8;font-weight:700;color:#1b3728">Total paid</td>
              <td style="padding:10px 0 0;border-top:1px solid #e8dfc8;text-align:right;font-weight:700;color:#1b3728;font-size:16px">{_esc(_money(getattr(order, "grand_total", 0)))}</td>
            </tr>
          </table>
          <p style="margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                     letter-spacing:0.12em;text-transform:uppercase;color:#a08b4a">Ship to</p>
          <p style="margin:0 0 20px;font-size:14px;line-height:1.55;color:#444;white-space:pre-line">{_esc(_order_address(order))}</p>
          <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:#555">
            We’ll write again when your package is on its way. Fulfillment usually leaves the warehouse within a few business days.
          </p>
          <p style="margin:0;text-align:center">{_btn(base, "Visit the shop")}</p>
        """,
    )
    ok = await send_email(to=email, subject=subject, text=text, html=html)

    # Owner notification (always separate from customer mail)
    owners = _notify_owner()
    if owners:
        phone = getattr(order, "phone", "") or "—"
        country = getattr(order, "shipping_country", "") or "—"
        city = getattr(order, "shipping_city", "") or ""
        province = getattr(order, "shipping_province", "") or ""
        origin_bits = [p for p in (city, province, country) if p and p != "—"]
        origin = ", ".join(origin_bits) if origin_bits else country
        owner_text = f"""New paid order #{oid}

Customer: {name}
Email: {email}
Phone: {phone}
Ship to / origin: {origin}

{_order_address(order)}

Items:
{_order_lines_text(items)}

Subtotal: {_money(getattr(order, "product_total", 0))}
Shipping: {_money(getattr(order, "shipping_total", 0))}
Total: {_money(getattr(order, "grand_total", 0))}

Source: {_public_base()}
"""
        owner_html = _wrap_html(
            preheader=f"New order #{oid} · {name} · {_money(getattr(order, 'grand_total', 0))}",
            eyebrow="Shop notification",
            body_html=f"""
              <h1 style="margin:0 0 10px;font-family:Georgia,serif;font-size:22px;color:#1b3728">
                New paid order
              </h1>
              <p style="margin:0 0 16px;font-size:15px;line-height:1.55;color:#333">
                Someone just completed checkout on <strong>{_esc(shop)}</strong>.
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                     style="margin:0 0 18px;font-family:Arial,Helvetica,sans-serif;font-size:14px">
                <tr>
                  <td style="padding:6px 0;color:#6b5c3e;width:38%">Order</td>
                  <td style="padding:6px 0;color:#1b3728;font-weight:700">#{_esc(oid)}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#6b5c3e">Buyer</td>
                  <td style="padding:6px 0;color:#1b3728">{_esc(name)}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#6b5c3e">Email</td>
                  <td style="padding:6px 0;color:#1b3728">
                    <a href="mailto:{_esc(email)}" style="color:#2b5240;text-decoration:none">{_esc(email)}</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#6b5c3e">Phone</td>
                  <td style="padding:6px 0;color:#1b3728">{_esc(phone)}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#6b5c3e">Ship / origin</td>
                  <td style="padding:6px 0;color:#1b3728">{_esc(origin)}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#6b5c3e;vertical-align:top">Address</td>
                  <td style="padding:6px 0;color:#1b3728;white-space:pre-line">{_esc(_order_address(order))}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#6b5c3e">Source</td>
                  <td style="padding:6px 0;color:#1b3728">{_esc(base)}</td>
                </tr>
              </table>
              <p style="margin:0 0 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                         letter-spacing:0.12em;text-transform:uppercase;color:#a08b4a">Items</p>
              <table role="presentation" width="100%" style="margin:0 0 14px">{_order_lines_html(items)}</table>
              <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:700;color:#1b3728">
                Total {_esc(_money(getattr(order, "grand_total", 0)))}
              </p>
            """,
        )
        await send_email(
            to=owners,
            subject=f"[TBW] New order #{oid} — {name} — {_money(getattr(order, 'grand_total', 0))}",
            text=owner_text,
            html=owner_html,
        )
    return ok


async def send_order_fulfillment_started(order: Any, items: list[Any]) -> bool:
    """Customer: order sent to warehouse / processing."""
    oid = getattr(order, "id", "?")
    email = getattr(order, "email", "") or ""
    name = getattr(order, "customer_name", "") or "there"
    shop = _shop_name()
    cj = getattr(order, "cj_order_number", "") or ""
    subject = f"Order #{oid} is being prepared — {shop}"
    text = f"""Hi {name},

Good news: order #{oid} has been submitted for fulfillment.
{f'Reference: {cj}' if cj else ''}

Items:
{_order_lines_text(items)}

We'll email you when tracking is available.

— {shop}
{_public_base()}
"""
    html = _wrap_html(
        preheader=f"Order #{oid} is being prepared",
        eyebrow="Fulfillment update",
        body_html=f"""
          <h1 style="margin:0 0 10px;font-family:Georgia,serif;font-size:24px;font-weight:600;color:#1b3728">
            We’re preparing your order
          </h1>
          <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#333">
            Hi {_esc(name)}, order <strong style="color:#1b3728">#{_esc(oid)}</strong> is with our
            fulfillment partner and will leave the warehouse soon.
          </p>
          {f"<p style='margin:0 0 16px;font-family:Arial,sans-serif;font-size:13px;color:#6b5c3e'>Reference: {_esc(cj)}</p>" if cj else ""}
          <p style="margin:0 0 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                     letter-spacing:0.12em;text-transform:uppercase;color:#a08b4a">Items</p>
          <table role="presentation" width="100%" style="margin:0 0 20px">{_order_lines_html(items)}</table>
          <p style="margin:0;font-size:14px;color:#555;line-height:1.6">
            We’ll email you again when tracking is available.
          </p>
        """,
    )
    return await send_email(to=email, subject=subject, text=text, html=html)


async def send_order_shipped(
    order: Any,
    items: list[Any],
    *,
    tracking_number: str = "",
    tracking_url: str = "",
    carrier: str = "",
) -> bool:
    """Customer: package shipped (call from admin when you have tracking)."""
    oid = getattr(order, "id", "?")
    email = getattr(order, "email", "") or ""
    name = getattr(order, "customer_name", "") or "there"
    shop = _shop_name()
    track_line = ""
    if tracking_number:
        track_line = f"Tracking: {tracking_number}"
        if carrier:
            track_line = f"{carrier} — {track_line}"
    if tracking_url:
        track_line = (track_line + f"\n{tracking_url}").strip()

    subject = f"Order #{oid} has shipped — {shop}"
    text = f"""Hi {name},

Your order #{oid} is on its way.

{track_line or "Tracking details will follow if not listed here."}

Items:
{_order_lines_text(items)}

— {shop}
{_public_base()}
"""
    track_html = ""
    if tracking_url:
        track_html = f"<p style='margin:16px 0;text-align:center'>{_btn(tracking_url, 'Track package')}</p>"
    if tracking_number:
        track_html += (
            f"<p style='margin:12px 0;font-family:Arial,sans-serif;font-size:14px;color:#444;text-align:center'>"
            f"<strong style='color:#1b3728'>Tracking:</strong> {_esc(tracking_number)}"
        )
        if carrier:
            track_html += f" · {_esc(carrier)}"
        track_html += "</p>"

    html = _wrap_html(
        preheader=f"Order #{oid} has shipped",
        eyebrow="On its way",
        body_html=f"""
          <h1 style="margin:0 0 10px;font-family:Georgia,serif;font-size:24px;font-weight:600;color:#1b3728">
            Your order has shipped
          </h1>
          <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#333">
            Hi {_esc(name)}, the package for order <strong style="color:#1b3728">#{_esc(oid)}</strong>
            is on the move — another chapter en route to your door.
          </p>
          {track_html}
          <p style="margin:16px 0 8px;font-family:Arial,Helvetica,sans-serif;font-size:11px;
                     letter-spacing:0.12em;text-transform:uppercase;color:#a08b4a">Items</p>
          <table role="presentation" width="100%" style="margin:0 0 12px">{_order_lines_html(items)}</table>
        """,
    )
    return await send_email(to=email, subject=subject, text=text, html=html)


async def send_cart_reminder(
    *,
    email: str,
    customer_name: str = "",
    lines: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Abandoned-cart style reminder (call from a cron/script when you detect
    a cart email with no completed order).
    """
    name = customer_name or "there"
    shop = _shop_name()
    base = _public_base()
    lines = lines or []
    items_txt = "\n".join(
        f"  • {x.get('title', 'Item')} ×{x.get('quantity', 1)}" for x in lines
    ) or "  • Items waiting in your cart"
    items_html = "".join(
        f"<li>{_esc(x.get('title', 'Item'))} ×{int(x.get('quantity') or 1)}</li>"
        for x in lines
    ) or "<li>Items waiting in your cart</li>"

    subject = f"You left something behind — {shop}"
    text = f"""Hi {name},

It looks like you left items in your cart at {shop}.

{items_txt}

Finish your order anytime:
{base}/cart.html

— {shop}
"""
    html = _wrap_html(
        preheader="Your cart is waiting",
        eyebrow="Still thinking it over?",
        body_html=f"""
          <h1 style="margin:0 0 10px;font-family:Georgia,serif;font-size:24px;font-weight:600;color:#1b3728">
            Your cart is waiting
          </h1>
          <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#333">
            Hi {_esc(name)}, a few reading companions are still holding your place.
          </p>
          <ul style="margin:0 0 20px;padding-left:1.2rem;font-size:15px;line-height:1.7;color:#2a2a2a">
            {items_html}
          </ul>
          <p style="margin:0;text-align:center">{_btn(f"{base}/cart.html", "Return to cart")}</p>
        """,
    )
    return await send_email(to=email, subject=subject, text=text, html=html)
