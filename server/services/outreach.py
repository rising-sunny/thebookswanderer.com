"""Explicit, once-per-source invitations with a durable delivery ledger."""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import os
import re
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.utils import make_msgid
from urllib.parse import urlencode

from email_validator import validate_email

from services import collaborators_store as store
from services import email as mail
from services.invitation import draft, SENDER
from services.collaborators import site_host
from urls import PUBLIC_BASE


def normalized_email(email: str) -> str:
    return validate_email(email, check_deliverability=False).normalized.lower()


def unsubscribe_token(email: str) -> str:
    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        raise ValueError("SECRET_KEY is required")
    return hmac.new(secret.encode(), ("outreach-unsubscribe:" + normalized_email(email)).encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_url(email: str, lang: str) -> str:
    return PUBLIC_BASE + "/api/outreach/unsubscribe?" + urlencode({"email": email, "t": unsubscribe_token(email), "lang": lang})


def valid_unsubscribe(email: str, token: str) -> bool:
    try:
        return hmac.compare_digest(unsubscribe_token(email).encode(), token.encode())
    except ValueError:
        return False


def global_contact_state(email: str) -> str:
    from database import SessionLocal
    from models import EmailOptOut, NewsletterSubscriber
    with SessionLocal() as db:
        if db.query(EmailOptOut).filter(EmailOptOut.email == email).first():
            return "opted_out"
        subscriber = db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == email).first()
        if subscriber:
            return "already_subscribed" if subscriber.active else "opted_out"
    return "eligible"


def suppress(email: str) -> None:
    email = normalized_email(email)
    with store.connect() as db:
        db.execute("INSERT OR IGNORE INTO outreach_suppressions(email,created_at) VALUES(?,?)", (email, store.now()))
        db.execute("UPDATE outreach_deliveries SET status='suppressed',detail='Baja solicitada' WHERE email=? AND status='queued'", (email,))
    # The private suppression is already durable even if the store DB is down.
    from database import SessionLocal
    from models import EmailOptOut, NewsletterSubscriber
    with SessionLocal() as db:
        if not db.query(EmailOptOut).filter(EmailOptOut.email == email).first():
            db.add(EmailOptOut(email=email, source="outreach_unsubscribe"))
        db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == email).update({"active": False})
        db.commit()


def locally_suppressed(email: str) -> bool:
    with store.connect() as db:
        return db.execute("SELECT 1 FROM outreach_suppressions WHERE email=?", (email,)).fetchone() is not None


def smtp_preflight() -> dict:
    absent = [key for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "SECRET_KEY") if not mail._env(key)]
    if absent:
        raise ValueError("Missing mail configuration: " + ", ".join(absent))
    sender = normalized_email(SENDER)
    port = int(mail._env("SMTP_PORT", "587"))
    use_ssl = port == 465 or mail._env("SMTP_SSL").lower() in ("1", "true", "yes")
    starttls = mail._env("SMTP_STARTTLS", "1").lower() not in ("0", "false", "no")
    if not use_ssl and not starttls:
        raise ValueError("SMTP authentication requires TLS")
    kwargs = {"host": mail._env("SMTP_HOST"), "port": port, "timeout": 20}
    context = ssl.create_default_context()
    connection = smtplib.SMTP_SSL(**kwargs, context=context) if use_ssl else smtplib.SMTP(**kwargs)
    with connection as server:
        server.ehlo()
        if not use_ssl:
            server.starttls(context=context)
            server.ehlo()
        server.login(mail._env("SMTP_USER"), mail._env("SMTP_PASSWORD"))
        code, _ = server.mail(sender)
        server.rset()
        if code != 250:
            raise ValueError("SMTP does not accept the campaign sender")
    return {"sender": sender, "smtp_tls_auth": "OK"}


def selected_candidates(candidate_ids: list[int]) -> list[dict]:
    if not candidate_ids or len(candidate_ids) > 20 or len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Select between 1 and 20 unique candidate IDs")
    with store.connect() as db:
        rows = [dict(r) for r in db.execute("SELECT c.*,s.active,s.lang,s.name,s.url AS site_url FROM candidates c JOIN sources s ON s.id=c.source_id WHERE c.id IN (" + ",".join("?" for _ in candidate_ids) + ") ORDER BY c.id", candidate_ids)]
    if len(rows) != len(candidate_ids):
        raise ValueError("A selected candidate is missing")
    if len({r["source_id"] for r in rows}) != len(rows):
        raise ValueError("Select only one address per source")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    for row in rows:
        if not row["active"] or row["status"] not in ("pending", "approved", "contacted"):
            raise ValueError("A selected candidate is paused or discarded")
        if datetime.fromisoformat(row["last_seen_at"]) < cutoff or not row["evidence"].strip():
            raise ValueError("A selected source needs a fresh review")
        row["email"] = normalized_email(row["email"])
    return rows


def prepare(campaign_id: str, rows: list[dict]) -> int:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", campaign_id):
        raise ValueError("Invalid campaign name")
    prepared = []
    for row in rows:
        state = "opted_out" if locally_suppressed(row["email"]) else global_contact_state(row["email"])
        content = draft(row["lang"], unsubscribe_url(row["email"], row["lang"]))
        prepared.append((row, state, content))
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO outreach_campaigns(id,created_at) VALUES(?,?)", (campaign_id, store.now()))
        added = 0
        for row, state, content in prepared:
            # A new campaign label cannot resend the same invitation to another
            # address of the same blog or to the same address under a new source.
            key = site_host(row["site_url"])
            if db.execute("SELECT 1 FROM outreach_deliveries WHERE email=? OR site_key=?", (row["email"], key)).fetchone():
                continue
            status = "queued" if state == "eligible" and row["status"] != "contacted" else "suppressed"
            detail = {"opted_out": "Baja previa", "already_subscribed": "Ya está suscrito"}.get(state, "Ya contactado" if row["status"] == "contacted" else "")
            db.execute("""INSERT INTO outreach_deliveries
                (campaign_id,candidate_id,source_id,site_key,email,lang,subject,html,text,message_id,status,created_at,detail)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (campaign_id, row["id"], row["source_id"], key, row["email"], row["lang"], content["subject"], content["html"], content["text"], make_msgid(domain=mail._env("MAIL_FROM").split("@")[-1]), status, store.now(), detail))
            if status == "queued":
                db.execute("UPDATE candidates SET status='approved',updated_at=? WHERE id=? AND status='pending'", (store.now(), row["id"]))
            added += 1
        return added


def deliver(campaign_id: str, pause_seconds: float = 3) -> dict:
    with store.connect() as db:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
        attempted = db.execute("SELECT count(*) FROM outreach_deliveries WHERE attempted_at>=?", (cutoff,)).fetchone()[0]
        remaining = max(0, 10 - attempted)
        rows = [dict(r) for r in db.execute("SELECT * FROM outreach_deliveries WHERE campaign_id=? AND status='queued' ORDER BY id LIMIT ?", (campaign_id, remaining))]
    for index, row in enumerate(rows):
        state = "opted_out" if locally_suppressed(row["email"]) else global_contact_state(row["email"])
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT c.status,s.active,c.email FROM candidates c JOIN sources s ON s.id=c.source_id WHERE c.id=?", (row["candidate_id"],)).fetchone()
            if state != "eligible" or not current or not current["active"] or current["status"] != "approved" or current["email"] != row["email"]:
                db.execute("UPDATE outreach_deliveries SET status='suppressed',detail='Baja, suscripción previa o contacto desactivado' WHERE id=? AND status='queued'", (row["id"],))
                continue
            cursor = db.execute("UPDATE outreach_deliveries SET status='sending',attempted_at=? WHERE id=? AND status='queued'", (store.now(), row["id"]))
            if not cursor.rowcount:
                continue
        # Recheck after committing the claim. No delivery is automatically
        # retried if a crash or transport failure leaves its outcome ambiguous.
        if locally_suppressed(row["email"]):
            with store.connect() as db:
                db.execute("UPDATE outreach_deliveries SET status='suppressed',detail='Baja solicitada' WHERE id=?", (row["id"],))
            continue
        link = unsubscribe_url(row["email"], row["lang"])
        try:
            accepted = mail._send_sync(to=[row["email"]], subject=row["subject"], text=row["text"], html=row["html"], message_id=row["message_id"], from_address=SENDER, reply_to=SENDER, headers={"List-Unsubscribe": f"<{link}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click", "X-TBW-Campaign": campaign_id})
        except Exception:
            accepted = False
        with store.connect() as db:
            db.execute("UPDATE outreach_deliveries SET status=?,sent_at=?,detail=? WHERE id=?", ("sent" if accepted else "uncertain", store.now() if accepted else None, "Aceptado por SMTP" if accepted else "SMTP no confirmó el envío; revisar antes de reintentar", row["id"]))
            if accepted:
                db.execute("UPDATE candidates SET status='contacted',updated_at=? WHERE id=?", (store.now(), row["candidate_id"]))
        if index + 1 < len(rows) and pause_seconds:
            time.sleep(pause_seconds)
    with store.connect() as db:
        db.execute("UPDATE outreach_campaigns SET last_run_at=? WHERE id=?", (store.now(), campaign_id))
        return {r["status"]: r["n"] for r in db.execute("SELECT status,count(*) AS n FROM outreach_deliveries WHERE campaign_id=? GROUP BY status", (campaign_id,))}


def auto_candidates(limit: int = 10) -> list[int]:
    with store.connect() as db:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
        rows = [dict(r) for r in db.execute("SELECT c.id,c.email,c.source_id,c.purpose,s.url,s.lang FROM candidates c JOIN sources s ON s.id=c.source_id WHERE s.active=1 AND c.status IN ('pending','approved') AND c.evidence!='' AND c.last_seen_at>=? ORDER BY c.id", (cutoff,))]
        contacted_emails = {r[0] for r in db.execute("SELECT email FROM outreach_deliveries")}
        contacted_sites = {r[0] for r in db.execute("SELECT site_key FROM outreach_deliveries")}
    chosen = {}
    # Prefer the site's professional-domain mailbox over an alternate free one.
    rows.sort(key=lambda r: (r["email"].split("@")[1] != site_host(r["url"]), r["id"]))
    for row in rows:
        key = site_host(row["url"])
        if row["email"] in contacted_emails or key in contacted_sites or key in chosen:
            continue
        chosen[key] = row["id"]
        if len(chosen) >= limit:
            break
    return list(chosen.values())


def run(campaign_id: str, candidate_ids: list[int], send: bool = False, automatic: bool = False) -> dict:
    store.init_store()
    with (store.data_dir() / "outreach.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another campaign sender is running")
        if automatic:
            candidate_ids = auto_candidates()
        rows = selected_candidates(candidate_ids) if candidate_ids else []
        preflight = smtp_preflight()
        if not send:
            states = ["opted_out" if locally_suppressed(r["email"]) else global_contact_state(r["email"]) for r in rows]
            return {"mode": "dry_run", **preflight, "selected": len(rows), "eligible": states.count("eligible"), "suppressed": len(rows) - states.count("eligible"), "languages": {lang: sum(r["lang"] == lang for r in rows) for lang in ("es", "en")}}
        with store.connect() as db:
            db.execute("UPDATE outreach_deliveries SET status='uncertain',detail='Proceso interrumpido; no se reintenta automáticamente' WHERE status='sending'")
        added = prepare(campaign_id, rows)
        totals = deliver(campaign_id)
        return {"mode": "send", "campaign": campaign_id, **preflight, "new_records": added, "totals": totals}
