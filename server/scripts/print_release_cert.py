#!/usr/bin/env python3
"""Print a certificate for the server's print-release key, to encrypt print bundles with.

The private key stays in DIGITAL_DIR/.release-private/; only the public
certificate is printed. Encrypt a bundle for install_print_bundle.py with:

  openssl cms -encrypt -binary -aes256 -outform DER -in bundle.zip -out print-bundle.enc release.crt
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from services import digital  # noqa: E402

key = digital.digital_dir() / ".release-private" / "lost-manuscript.pem"
if not key.is_file():
    raise SystemExit("release key missing")
with tempfile.TemporaryDirectory() as tmp:
    crt = Path(tmp) / "release.crt"
    subprocess.run(["openssl", "req", "-new", "-x509", "-key", str(key), "-subj", "/CN=tbw-print-release",
                    "-days", "3650", "-out", str(crt)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(crt.read_text())
