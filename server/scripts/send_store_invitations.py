#!/usr/bin/env python3
"""Explicitly send the approved invitation once to selected professional contacts.

Default is a dry run (TLS/authentication and suppression checks, no mail).
--send authorizes the explicit candidate IDs, queues them and sends individually.
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from services import outreach


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--candidate-ids", default="", help="Comma-separated explicitly reviewed IDs")
    parser.add_argument("--auto", action="store_true", help="Select fresh professional contacts automatically, once per site")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    try:
        if not args.auto and not args.candidate_ids:
            raise ValueError("Select candidate IDs or automatic selection")
        ids = [int(value) for value in args.candidate_ids.split(",") if value]
        result = outreach.run(args.campaign, ids, args.send, args.auto)
    except Exception as exc:
        # Never echo SMTP exceptions, tokens, addresses or message bodies.
        detail = str(exc) if type(exc) is ValueError else "No se completó el envío; revisar la configuración y el registro privado."
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "detail": detail}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get("totals", {}).get("uncertain") else 0


if __name__ == "__main__":
    raise SystemExit(main())
