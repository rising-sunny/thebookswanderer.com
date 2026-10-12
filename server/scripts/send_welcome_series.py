#!/usr/bin/env python3
"""Newsletter welcome series: 1) the free 2027 Reading Challenge, 2) the
Reading Passport three days later, 3) the gift guide four days after that.

Step 1 normally goes out at signup (main.py); this catches the ones that
failed and subscribers from before the series existed. Cron runs it hourly.

  python scripts/send_welcome_series.py            # send what is due
  python scripts/send_welcome_series.py --dry-run  # list only
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from database import SessionLocal, init_db  # noqa: E402
from models import EmailOptOut, NewsletterSubscriber  # noqa: E402
from services import email as email_service  # noqa: E402

MAX_PER_RUN = 60  # keep SMTP providers happy


async def main() -> int:
    import main as app_main

    dry = "--dry-run" in sys.argv
    init_db()
    db = SessionLocal()
    opted_out = {e.email for e in db.query(EmailOptOut).all()}
    now = datetime.utcnow()
    due = []
    for sub in db.query(NewsletterSubscriber).filter(NewsletterSubscriber.active.is_(True)).all():
        if sub.email in opted_out:
            continue
        step = (sub.welcome_step or 0) + 1
        if step > 3:
            continue
        if step > 1 and (not sub.welcome_at or now - sub.welcome_at < timedelta(days=email_service.WELCOME_DELAYS_DAYS[step])):
            continue
        due.append((sub, step))
    print(f"{now:%Y-%m-%d %H:%M} {len(due)} welcome letter(s) due")
    for sub, step in due[:MAX_PER_RUN]:
        print(f"  {sub.email} [{sub.lang}] step {step}")
        if not dry:
            await app_main._send_welcome_step(sub.id, step)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
