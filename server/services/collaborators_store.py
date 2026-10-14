"""Private research database, deliberately separate from newsletter subscribers."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


STATUSES = ("pending", "approved", "discarded", "contacted")
SEEDS = (
    ("Gina Rae Mitchell", "https://ginaraemitchell.com/work-with-me/", "en", "Blog literario", "Reseñas, presentaciones de libros y propuestas de colaboración."),
    ("The Diary of a Reader", "https://thediaryofareader.com/work-with-me/", "en", "Blog literario", "Libros y creación de contenido para audiencias lectoras."),
    ("The Second Draft", "https://the-second-draft.com/work-with-me/", "en", "Blog literario", "Reseñas de libros y colaboraciones con autores."),
    ("The Literary Lifestyle", "https://theliterarylifestyle.com/about/contact/", "en", "Blog literario", "Lecturas y estilo de vida para lectores."),
    ("Caerellia", "https://www.caerellia.com/p/contacto.html", "es", "Blog literario", "Reseñas y entrevistas; recibe propuestas de autores y editoriales."),
    ("Modus Leyendi", "https://www.modusleyendi.com/p/contacto_10.html", "es", "Blog literario", "Reseñas y colaboraciones con autores y editoriales."),
    ("Perdido Entre Los Libros", "https://perdidoentreloslibros.blogspot.com/p/contacto.html", "es", "Blog literario", "Reseñas; acepta propuestas de empresas, editoriales y autores."),
    ("Carmen en su tinta", "https://carmenensutinta.blogspot.com/p/contacto.html", "es", "Blog literario", "Comunidad lectora con una política pública de colaboraciones."),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_dir() -> Path:
    return Path(os.getenv("COLLABORATORS_DATA_DIR", "/var/lib/tbw-collaborators"))


@contextmanager
def connect():
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(folder / "research.db", timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_store() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
            lang TEXT NOT NULL, category TEXT NOT NULL, reason TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, checked_at TEXT,
            discovery_checked_at TEXT, origin TEXT NOT NULL DEFAULT 'manual',
            last_status TEXT NOT NULL DEFAULT 'Pendiente de revisión'
        );
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
            email TEXT NOT NULL UNIQUE, source_url TEXT NOT NULL, evidence TEXT NOT NULL,
            purpose TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','approved','discarded','contacted')),
            notes TEXT NOT NULL DEFAULT '', found_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running', sites INTEGER NOT NULL DEFAULT 0,
            found INTEGER NOT NULL DEFAULT 0, added INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS outreach_campaigns (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, last_run_at TEXT
        );
        CREATE TABLE IF NOT EXISTS outreach_deliveries (
            id INTEGER PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES outreach_campaigns(id),
            candidate_id INTEGER NOT NULL REFERENCES candidates(id), source_id INTEGER NOT NULL,
            site_key TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL, lang TEXT NOT NULL, subject TEXT NOT NULL,
            html TEXT NOT NULL, text TEXT NOT NULL, message_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','sending','sent','suppressed','uncertain')),
            created_at TEXT NOT NULL, attempted_at TEXT, sent_at TEXT,
            detail TEXT NOT NULL DEFAULT '',
            UNIQUE(campaign_id,email), UNIQUE(campaign_id,source_id)
        );
        CREATE TABLE IF NOT EXISTS outreach_suppressions (
            email TEXT PRIMARY KEY, created_at TEXT NOT NULL
        );
        """)
        # Existing research installations predate autonomous source discovery.
        columns = {r["name"] for r in db.execute("PRAGMA table_info(sources)")}
        if "discovery_checked_at" not in columns:
            db.execute("ALTER TABLE sources ADD COLUMN discovery_checked_at TEXT")
        if "origin" not in columns:
            db.execute("ALTER TABLE sources ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'")


def seed_sources() -> int:
    with connect() as db:
        before = db.total_changes
        db.executemany("INSERT OR IGNORE INTO sources(name,url,lang,category,reason) VALUES(?,?,?,?,?)", SEEDS)
        return db.total_changes - before


def save_candidate(db, source_id: int, item: dict) -> bool:
    stamp = now()
    cursor = db.execute("""INSERT OR IGNORE INTO candidates
        (source_id,email,source_url,evidence,purpose,found_at,last_seen_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)""", (source_id, item["email"], item["source_url"], item["evidence"], item["purpose"], stamp, stamp, stamp))
    if cursor.rowcount:
        return True
    # Never reset a decision or overwrite notes when the same email is seen again.
    db.execute("UPDATE candidates SET last_seen_at=? WHERE email=?", (stamp, item["email"]))
    if item["evidence"]:
        db.execute("UPDATE candidates SET source_url=?,evidence=?,purpose=? WHERE email=? AND source_id=?", (item["source_url"], item["evidence"], item["purpose"], item["email"], source_id))
    return False


def snapshot(status: str = "", lang: str = "", limit: int | None = 500) -> dict:
    with connect() as db:
        clauses, values = [], []
        if status:
            clauses.append("c.status=?")
            values.append(status)
        if lang:
            clauses.append("s.lang=?")
            values.append(lang)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = """SELECT c.*, s.name, s.lang, s.category, s.reason, s.url AS site_url
                   FROM candidates c JOIN sources s ON s.id=c.source_id"""
        limit_sql = "" if limit is None else " LIMIT ?"
        if limit is not None:
            values.append(limit)
        candidates = [dict(r) for r in db.execute(query + where + " ORDER BY c.found_at DESC,c.id DESC" + limit_sql, values)]
        counts = {s: 0 for s in STATUSES}
        counts.update({r["status"]: r["n"] for r in db.execute("SELECT status,count(*) AS n FROM candidates GROUP BY status")})
        return {
            "candidates": candidates, "counts": counts,
            "sources": [dict(r) for r in db.execute("SELECT * FROM sources ORDER BY lang,name")],
            "runs": [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 10")],
            "campaigns": [dict(r) for r in db.execute("SELECT c.id,c.created_at,c.last_run_at,d.status,count(d.id) AS total FROM outreach_campaigns c LEFT JOIN outreach_deliveries d ON d.campaign_id=c.id GROUP BY c.id,d.status ORDER BY c.created_at DESC")],
            "deliveries": [dict(r) for r in db.execute("SELECT d.id,d.campaign_id,d.candidate_id,d.email,d.lang,d.status,d.created_at,d.attempted_at,d.sent_at,d.detail,s.name FROM outreach_deliveries d JOIN sources s ON s.id=d.source_id ORDER BY d.id DESC LIMIT 100")],
        }
