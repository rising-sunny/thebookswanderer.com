#!/usr/bin/env python3
"""Run the one-time tasks in release_queue.json, each once. Called by deploy/remote-setup.sh as www-data.

Each task is {"id": ..., "script": "<file in server/scripts>", "args": [...]}. Finished ids are
kept in DIGITAL_DIR/.release-private/queue-done.json; a failed task is retried on the next deploy.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import digital  # noqa: E402

QUEUE = Path(__file__).with_name("release_queue.json")
DONE = digital.digital_dir() / ".release-private" / "queue-done.json"

done = set(json.loads(DONE.read_text())) if DONE.exists() else set()
for task in json.loads(QUEUE.read_text()) if QUEUE.exists() else []:
    if task["id"] in done:
        continue
    script = Path(__file__).with_name(task["script"])
    print(f"== {task['id']}: {task['script']} {' '.join(task.get('args', []))}", flush=True)
    try:
        ok = subprocess.run([sys.executable, str(script), *task.get("args", [])], cwd=ROOT, timeout=600).returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
    print(f"== {task['id']}: {'done' if ok else 'FAILED, will retry on the next deploy'}", flush=True)
    if not ok:
        break  # later tasks may depend on this one
    done.add(task["id"])
    DONE.write_text(json.dumps(sorted(done)))
