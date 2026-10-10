"""CJ recovery: local report by default; never creates orders."""
import argparse
import asyncio
from collections import Counter
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from database import SessionLocal
from models import Order, OrderItem
from services import cj

PENDING = ("paid", "cj_submitting", "cj_review")


def match_cj(data, order_id, items):
    if not isinstance(data, list):
        raise ValueError("Unexpected CJ response")
    if not data:
        return None
    if len(data) != 1:
        raise ValueError("Multiple CJ orders; manual review required")

    row = data[0]
    if not isinstance(row, dict) or not row.get("orderId"):
        raise ValueError("CJ identifier missing")
    if row.get("orderStatus") == "CANCELLED":
        raise ValueError("CJ order cancelled; manual review required")

    expected = Counter(
        (f"tbw-{order_id}-{item.id}", str(item.cj_vid), item.quantity)
        for item in items
    )
    actual = Counter(
        (str(line.get("storeLineItemId") or ""),
         str(line.get("vid") or ""),
         int(line.get("quantity") or 0))
        for line in row.get("productList") or []
    )
    if not expected or actual != expected:
        raise ValueError("CJ items do not match; manual review required")
    return row


async def run(args):
    with SessionLocal() as db:
        query = db.query(Order).filter(Order.status.in_(PENDING))
        if args.order_id is not None:
            query = query.filter(Order.id == args.order_id)
        orders = query.order_by(Order.id).all()

        if not orders:
            print("No hay pedidos pendientes de recuperación.")
            return

        for order in orders:
            print(f"Pedido {order.id}: {order.status}")
            if order.cj_order_id:
                print("  Ya tiene identificador CJ; revisar su estado.")
                continue
            if not (args.check or args.link):
                print("  Solo informe local; no se consultó CJ.")
                continue

            original_status = order.status
            items = db.query(OrderItem).filter(
                OrderItem.order_id == order.id
            ).all()

            try:
                data = await cj._request(
                    "POST",
                    "/shopping/order/getOrderDetailBatch",
                    json_body={"orderIds": [f"TBW-{order.id}"]},
                )
                row = match_cj(data, order.id, items)
            except Exception:
                print("  Consulta fallida o ambigua; no se cambió nada.")
                continue

            if row is None:
                print("  CJ no devolvió coincidencia.")
                print("  No se crea ni se reenvía ningún pedido.")
                continue

            print("  CJ tiene el pedido y sus artículos coinciden.")
            if not args.link:
                print("  Consulta solamente; base sin cambios.")
                continue

            updated = (
                db.query(Order)
                .filter(
                    Order.id == order.id,
                    Order.status == original_status,
                    (Order.cj_order_id == "") |
                    (Order.cj_order_id.is_(None)),
                )
                .update(
                    {
                        "cj_order_id": str(row["orderId"]),
                        "cj_order_number": str(
                            row.get("cjOrderCode") or
                            row.get("orderNum") or ""
                        ),
                        "status": "cj_submitted",
                    },
                    synchronize_session=False,
                )
            )
            if updated == 1:
                db.commit()
                print("  Vinculación recuperada; sin crear pedido ni enviar correo.")
            else:
                db.rollback()
                print("  El pedido cambió durante la revisión; sin modificaciones.")

            await asyncio.sleep(0.6)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--order-id", type=int)
mode = parser.add_mutually_exclusive_group()
mode.add_argument("--check", action="store_true",
                  help="Consulta CJ; no modifica pedidos")
mode.add_argument("--link", action="store_true",
                  help="Vincula un pedido existente en CJ; no crea pedidos")
args = parser.parse_args()

if args.link and args.order_id is None:
    parser.error("--link requiere --order-id para recuperar un solo pedido")

asyncio.run(run(args))
