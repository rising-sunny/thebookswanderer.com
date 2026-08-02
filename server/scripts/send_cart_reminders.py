#!/usr/bin/env python3
"""
Recordatorio de carrito abandonado.

QUE CUENTA COMO ABANDONADO
El carrito vive en el navegador, asi que de la mayoria de visitantes no
tenemos email y no hay nada que enviar. Lo que si tenemos es el checkout
abandonado: al pulsar "Pay with PayPal" se crea una Order con email y
status="pending", y si el pago no se completa se queda ahi. Ese es el
segmento que se recupera con un email, y ademas el mas valioso: ya habian
puesto la direccion.

QUE NO HACE
No persigue a nadie. Un email por pedido y punto: cart_reminder_sent_at
se marca al enviarlo. Quien se da de baja entra en email_opt_outs y no
vuelve a recibir nada.

USO
    python3 scripts/send_cart_reminders.py --dry-run     # ver a quien iria
    python3 scripts/send_cart_reminders.py               # enviar
    python3 scripts/send_cart_reminders.py --hours 6     # esperar mas

CRON (cada hora)
    0 * * * * cd /var/www/thebookswanderer.com/server && \
      .venv/bin/python3 scripts/send_cart_reminders.py >> /var/log/tbw-cart.log 2>&1
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from database import SessionLocal, init_db  # noqa: E402
from models import EmailOptOut, Order, OrderItem  # noqa: E402
from services import email as email_service  # noqa: E402

# Estados que significan "ya pago": nunca se les recuerda nada.
PAID = ("paid", "cj_submitted", "fulfilled", "shipped", "refunded", "cancelled")


def _public_base() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or "https://thebookswanderer.com").rstrip("/")


def _unsubscribe_url(email: str) -> str:
    from main import unsubscribe_token

    normalized = email.strip().lower()
    return (
        f"{_public_base()}/api/unsubscribe"
        f"?email={quote(normalized)}&t={unsubscribe_token(normalized)}"
    )


def find_abandoned(db, hours: int, max_days: int) -> list[Order]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=hours)
    floor = now - timedelta(days=max_days)

    rows = (
        db.query(Order)
        .filter(
            Order.status.notin_(PAID),
            Order.email != "",
            Order.cart_reminder_sent_at.is_(None),
            Order.created_at <= cutoff,
            Order.created_at >= floor,
        )
        .order_by(Order.created_at.asc())
        .all()
    )

    # Si esa persona ya compro despues, no tiene sentido recordarle nada.
    opted = {e[0] for e in db.query(EmailOptOut.email).all()}
    salida = []
    for order in rows:
        mail = (order.email or "").strip().lower()
        if mail in opted:
            continue
        compro = (
            db.query(Order)
            .filter(Order.email == order.email, Order.status.in_(PAID))
            .first()
        )
        if compro:
            continue
        salida.append(order)
    return salida


async def run(hours: int, max_days: int, dry_run: bool, limit: int) -> int:
    init_db()
    db = SessionLocal()
    try:
        pendientes = find_abandoned(db, hours, max_days)[:limit]
        if not pendientes:
            print("Sin carritos abandonados que avisar.")
            return 0

        if not dry_run and not email_service.configured():
            print("SMTP no configurado: no se envia nada.")
            return 1

        enviados = 0
        for order in pendientes:
            items = (
                db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
            )
            lines = [
                {"title": it.title, "quantity": it.quantity} for it in items
            ]
            edad = datetime.now(timezone.utc).replace(tzinfo=None) - order.created_at
            print(
                f"#{order.id:<5} {order.email:<34} "
                f"{len(lines)} linea(s)  ${order.grand_total or 0:.2f}  "
                f"hace {int(edad.total_seconds() // 3600)}h"
            )
            if dry_run:
                continue

            ok = await email_service.send_cart_reminder(
                email=order.email,
                customer_name=order.customer_name or "",
                lines=lines,
                unsubscribe_url=_unsubscribe_url(order.email),
            )
            if ok:
                order.cart_reminder_sent_at = datetime.now(timezone.utc).replace(
                    tzinfo=None
                )
                db.commit()
                enviados += 1
            else:
                print(f"  fallo el envio a #{order.id}, se reintentara")

        if dry_run:
            print(f"\n[dry-run] {len(pendientes)} recordatorio(s) se enviarian.")
        else:
            print(f"\n{enviados} recordatorio(s) enviado(s).")
        return 0
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Recordatorios de carrito abandonado.")
    ap.add_argument("--hours", type=int, default=int(os.getenv("CART_REMINDER_HOURS", "3")),
                    help="Horas a esperar antes de avisar (por defecto 3).")
    ap.add_argument("--max-days", type=int, default=7,
                    help="No avisar de pedidos mas antiguos que esto (por defecto 7).")
    ap.add_argument("--limit", type=int, default=50,
                    help="Maximo de emails por ejecucion.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Muestra a quien se enviaria, sin enviar.")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.hours, args.max_days, args.dry_run, args.limit)))


if __name__ == "__main__":
    main()
