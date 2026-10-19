"""Once-only Lulu submission with a durable pre-POST claim and read-only recovery.

external_id is a lookup reference, not an API idempotency guarantee. After a
POST starts, a failed/ambiguous response must never lead to another POST.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urlencode

from sqlalchemy.exc import IntegrityError

from models import LuluSubmission
from services import lulu


class Pending(lulu.LuluError):
    pass


async def find_job(external_id: str):
    """Follow every search-result page and require an exact reference match."""
    matches = {}
    page = 1
    while True:
        data = await lulu.request('GET', '/print-jobs/?' + urlencode({
            'search': external_id, 'page': page, 'page_size': 100,
        }))
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            raise Pending('Lulu lookup returned an unexpected response; submission held')
        for job in data['results']:
            if job.get('external_id') == external_id:
                if not job.get('id'):
                    raise Pending('Lulu lookup returned a job without an ID; submission held')
                matches[str(job['id'])] = job
        if len(matches) > 1:
            raise Pending('Multiple Lulu jobs match the order; manual review required')
        if not data.get('next'):
            return next(iter(matches.values()), None)
        if not data['results'] or page >= 1000:
            raise Pending('Lulu search pagination did not complete; submission held')
        # Never follow an arbitrary next URL with an Authorization header.
        page += 1


def _verify_lines(job, lines):
    expected = sorted((ln['external_id'], int(ln['quantity'])) for ln in lines)
    try:
        actual = sorted((ln['external_id'], int(ln['quantity'])) for ln in job['line_items'])
    except (KeyError, TypeError, ValueError):
        raise Pending('Existing Lulu job has incomplete line references; manual review required') from None
    if actual != expected:
        raise Pending('Existing Lulu job lines differ from the order; manual review required')
    packages = {ln['external_id']: ln.get('pod_package_id') for ln in lines}
    for ln in job['line_items']:
        package = (ln.get('printable_normalization') or {}).get('pod_package_id')
        if package and packages.get(ln['external_id']) and package != packages[ln['external_id']]:
            raise Pending('Existing Lulu job has a different print package; manual review required')


def _accept(db, order, claim, job):
    job_id = str(job['id'])
    claim.state = 'submitted'
    claim.job_id = job_id
    claim.error_kind = ''
    order.lulu_job_id = job_id
    # The local job ID and submission state are committed together.
    db.commit()
    return job_id


async def reconcile(db, order, lines, *, apply=False):
    """Read-only at Lulu: optionally restore a verified local mapping, never POST."""
    if order.lulu_job_id:
        return True
    job = await find_job(f'tbw-{order.id}')
    if not job:
        return False
    _verify_lines(job, lines)
    if apply:
        claim = db.get(LuluSubmission, order.id)
        if claim is None:
            claim = LuluSubmission(order_id=order.id)
            db.add(claim)
        _accept(db, order, claim, job)
    return True


async def submit(db, order, lines, address, *, shipping_level=None):
    if order.lulu_job_id:
        return order.lulu_job_id
    external_id = f'tbw-{order.id}'
    manifest = {'lines': lines, 'address': address}
    if shipping_level:
        manifest['shipping_level'] = shipping_level
    digest = hashlib.sha256(json.dumps(manifest,
                                      sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    claim = db.get(LuluSubmission, order.id)
    owns_claim = False
    if claim is None:
        claim = LuluSubmission(order_id=order.id, state='checking', manifest_hash=digest)
        db.add(claim)
        try:
            db.commit()
            owns_claim = True
        except IntegrityError:
            db.rollback()
            claim = db.get(LuluSubmission, order.id)
    elif claim.state == 'retryable':
        owns_claim = bool(db.query(LuluSubmission).filter(
            LuluSubmission.order_id == order.id, LuluSubmission.state == 'retryable'
        ).update({'state': 'checking', 'manifest_hash': digest, 'error_kind': ''}, synchronize_session=False))
        db.commit()
        db.refresh(claim)
    if claim is None:
        raise Pending('Lulu submission claim unavailable; held for review')
    try:
        existing = await find_job(external_id)
        if existing:
            _verify_lines(existing, lines)
            return _accept(db, order, claim, existing)
    except Exception:
        if owns_claim:
            claim.state = 'retryable'  # No POST has been attempted.
            claim.error_kind = 'lookup_failed'
            db.commit()
        raise
    if not owns_claim:
        raise Pending('Lulu creation is in progress or uncertain; no second submission was sent')
    # Persist the uncertainty boundary BEFORE the POST. A process crash here
    # can require review, but cannot cause an automatic duplicate.
    transitioned = db.query(LuluSubmission).filter(
        LuluSubmission.order_id == order.id,
        LuluSubmission.state == 'checking',
        LuluSubmission.manifest_hash == digest,
    ).update({'state': 'submitting'}, synchronize_session=False)
    db.commit()
    db.refresh(claim)
    if not transitioned:
        raise Pending('Lulu submission state changed during lookup; no creation was sent')
    try:
        if shipping_level:
            result = await lulu.create_print_job(external_id, lines, address, shipping_level=shipping_level)
        else:
            result = await lulu.create_print_job(external_id, lines, address)
        if not isinstance(result, dict) or not result.get('id'):
            raise Pending('Lulu creation returned no job ID; reconciliation required')
        return _accept(db, order, claim, result)
    except Exception as exc:
        db.rollback()
        claim = db.get(LuluSubmission, order.id)
        if claim:
            claim.state = 'uncertain'
            claim.error_kind = type(exc).__name__[:80]
            db.commit()
        raise Pending('Lulu creation result is uncertain; reconcile before any further action') from None
