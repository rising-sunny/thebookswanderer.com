"""Freeze the paid order's exact artwork and lines; claim before the only POST.

No automatic resend after a timeout/crash. A read-only reconciliation by supplier
ID may restore an uncertain claim. Prodigi also receives a persistent UUID key.
"""
from __future__ import annotations
import json
import re
import uuid
from models import OrderItem, Product, ProductVariant, ProdigiSubmission
from services import prodigi_store as prodigi


def prepare(db, order, base):
    items = db.query(OrderItem).filter_by(order_id=order.id).all()
    products = {p.id:p for p in db.query(Product).filter(Product.id.in_([i.product_id for i in items]))}
    selected = [i for i in items if getattr(products.get(i.product_id), 'supplier', '') == 'prodigi']
    if not selected:
        return None
    if db.get(ProdigiSubmission, order.id):
        raise prodigi.ProdigiError('Prodigi manifest already frozen')
    lines=[]
    for item in selected:
        variant=db.get(ProductVariant,item.variant_id) if item.variant_id else None
        line=prodigi.quote_line(products[item.product_id],variant,item.quantity)
        line.update({'merchantReference':f'tbw-{order.id}-{item.id}', 'sizing':'fillPrintArea',
                     'assets':[{'printArea':'default','url':prodigi.asset_url(base)}]})
        lines.append(line)
    payload={'merchantReference':f'tbw-{order.id}', 'idempotencyKey':str(uuid.uuid4()),
             'shippingMethod':'Standard','recipient':prodigi.recipient(order),'items':lines}
    claim=ProdigiSubmission(order_id=order.id,payload_json=json.dumps(payload,sort_keys=True),state='prepared')
    db.add(claim)
    db.flush()
    return claim


def validate_remote(remote, payload, *, allow_minimal=False):
    if not isinstance(remote,dict) or not re.fullmatch(r'ord_[A-Za-z0-9_-]{1,100}',str(remote.get('id',''))):
        raise prodigi.ProdigiError('Prodigi returned no order ID')
    for field in ['idempotencyKey','merchantReference']:
        if field in remote and remote[field] != payload[field]:
            raise prodigi.ProdigiError('Prodigi order identity mismatch')
    if not allow_minimal and (remote.get('idempotencyKey') != payload['idempotencyKey']
                             or remote.get('merchantReference') != payload['merchantReference']):
        raise prodigi.ProdigiError('Prodigi order identity incomplete')
    if 'items' in remote:
        def signature(item):
            return (item.get('merchantReference'),item.get('sku'),item.get('copies'),
                    json.dumps(item.get('attributes',{}),sort_keys=True),
                    tuple(sorted((a.get('printArea'),a.get('url')) for a in item.get('assets',[]))))
        if sorted(map(signature,remote['items'])) != sorted(map(signature,payload['items'])):
            raise prodigi.ProdigiError('Prodigi order lines mismatch')
    elif not allow_minimal:
        raise prodigi.ProdigiError('Prodigi order lines incomplete')


def accept(db,order,claim,remote,outcome):
    claim.order_ref=remote['id'];claim.state='submitted';claim.error_kind=''
    order.prodigi_order_id=remote['id']
    if outcome=='createdwithissues':
        order.notes=((order.notes or '')+'\nProdigi accepted with issues; review in supplier dashboard.')[-2000:]
    db.commit()
    return remote['id']


async def submit(db,order):
    if order.status not in {'paid','cj_submitted','shipped','fulfilled'} or not order.paypal_order_id:
        raise prodigi.ProdigiError('Prodigi requires a confirmed paid order')
    if order.prodigi_order_id:
        return order.prodigi_order_id
    if not prodigi.ready():
        raise prodigi.ProdigiError('Prodigi submission unavailable')
    claim=db.get(ProdigiSubmission,order.id)
    if not claim:
        raise prodigi.ProdigiError('Frozen Prodigi manifest missing')
    if claim.state=='submitted' and claim.order_ref:
        order.prodigi_order_id=claim.order_ref;db.commit();return claim.order_ref
    payload=json.loads(claim.payload_json)
    claimed=db.query(ProdigiSubmission).filter_by(order_id=order.id,state='prepared').update(
        {'state':'submitting'},synchronize_session=False)
    db.commit();db.refresh(claim)
    if not claimed:
        raise prodigi.ProdigiError('Prodigi submission needs reconciliation; no duplicate sent')
    try:
        data=await prodigi.request('POST','/orders',payload)
        outcome=str(data.get('outcome','')).lower()
        if outcome not in {'created','onhold','createdwithissues','alreadyexists'}:
            raise prodigi.ProdigiError('Prodigi submission needs review')
        remote=data.get('order',{})
        validate_remote(remote,payload,allow_minimal=outcome in {'created','onhold'})
        return accept(db,order,claim,remote,outcome)
    except Exception as exc:
        db.rollback();claim=db.get(ProdigiSubmission,order.id)
        claim.state='uncertain';claim.error_kind=type(exc).__name__[:80];db.commit()
        raise prodigi.ProdigiError('Prodigi result uncertain; reconcile before resubmission') from None


async def reconcile(db,order,supplier_id):
    """GET only. Verify persistent key and exact lines before restoring mapping."""
    if not re.fullmatch(r'ord_[A-Za-z0-9_-]{1,100}',supplier_id):
        raise prodigi.ProdigiError('Invalid supplier order ID')
    claim=db.get(ProdigiSubmission,order.id)
    if not claim:
        raise prodigi.ProdigiError('No frozen manifest')
    data=await prodigi.request('GET','/orders/'+supplier_id)
    if str(data.get('outcome','')).lower()!='ok':
        raise prodigi.ProdigiError('Supplier lookup unavailable')
    remote=data.get('order',{})
    validate_remote(remote,json.loads(claim.payload_json))
    return accept(db,order,claim,remote,'reconciled')
