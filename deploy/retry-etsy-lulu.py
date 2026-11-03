#!/usr/bin/env python3
"""One-time: let the unified Etsy -> Lulu worker submit receipt 4220948340 again.

The worker marks a receipt "uncertain" just before POST /print-jobs/ and only moves it to
"submitted" when Lulu returns a job id. That POST failed without an id on 2026-11-02, and Lulu
shows no job since 2026-11-01, so the entry is cleared and the worker runs once. Before
creating, the worker re-reads the Etsy receipt, checks Lulu for an existing job for this receipt
(remote_review instead of a duplicate), verifies the PDFs and quotes. It never calls a payment
endpoint: the job waits in Lulu for the owner to pay by hand.

Only that receipt is touched, only if it is still "uncertain" without a job id, under the worker's
own lock, with a backup of state.json. Output is masked: no buyer name, address or email.
"""
import fcntl
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

RID = "4220948340"
UNIFIED = Path("/opt/etsy_lulu_fulfill/lulu_books/unified")
CONFIG = UNIFIED / "config.json"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CAP = re.compile(r"\b[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+){1,3}\b")
STREET = re.compile(r"\b\d{1,6}\s+[A-Za-z][\w .'-]{1,40}\b(street|st|avenue|ave|drive|dr|road|rd|lane|ln|blvd|way|court|ct|place|pl)\b", re.I)


def mask(text):
    return CAP.sub("<name>", STREET.sub("<street>", EMAIL.sub("<email>", text)))


config = json.loads(CONFIG.read_text())
base = Path(config["state_dir"])
state_path = base / "state.json"

with (base / ".lock").open("a") as lock:
    for _ in range(60):                      # wait for a running cron pass to finish
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            time.sleep(5)
    else:
        raise SystemExit("worker busy for 5 minutes; nothing changed")
    state = json.loads(state_path.read_text())
    entry = state["receipts"].get(RID)
    if not entry or entry.get("status") != "uncertain" or entry.get("job_id"):
        print("receipt", RID, "is", (entry or {}).get("status"), (entry or {}).get("job_id"), "- nothing changed")
        raise SystemExit(0)
    backup = state_path.with_name(f"state.before-retry-{RID}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
    shutil.copy2(state_path, backup)
    del state["receipts"][RID]
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.chmod(tmp, 0o600)
    os.replace(tmp, state_path)
    print("cleared the uncertain entry; backup", backup.name)
    fcntl.flock(lock, fcntl.LOCK_UN)

for attempt in range(12):                    # the worker takes its own non-blocking lock
    run = subprocess.run(["/usr/bin/python3", str(UNIFIED / "worker.py"), "--config", str(CONFIG), "check"],
                         capture_output=True, text=True, timeout=600, cwd=str(UNIFIED))
    if "BlockingIOError" not in run.stderr:
        break
    time.sleep(10)
print("worker exit", run.returncode)
for line in run.stdout.splitlines():
    if RID in line or "needs_review" in line or "Error" in line:
        print("  out:", mask(line)[:300])
for line in run.stderr.splitlines()[-12:]:
    print("  err:", mask(line)[:300])
after = json.loads(state_path.read_text())["receipts"].get(RID, {})
print("receipt now:", after.get("status"), "job", after.get("job_id", "-"), "reason", after.get("reason", "-"),
      "existing", after.get("existing_job_ids", "-"))
