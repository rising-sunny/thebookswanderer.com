#!/usr/bin/env python3
"""Encrypted inbox for paid digital files (the repository is public).

Run as root on each deploy (deploy/remote-setup.sh):
1. If the inbox key is missing, create an RSA-4096 key in /etc/tbw-digital-inbox/ (root only)
   and print the PUBLIC key, so files can be encrypted to this server.
2. For each entry in deploy/inbox/inbox.json not yet installed: unwrap the AES key with the
   private key, decrypt the file, check its SHA-256, store it in the digital files folder
   (www-data, 0640), set it as the product's file and run digital_products.py --apply for
   that slug, which activates the product only when its file exists.

Encrypt on the sender side with the public key:
  openssl rand -out k.bin 32
  openssl pkeyutl -encrypt -pubin -inkey inbox.pub -pkeyopt rsa_padding_mode:oaep \
      -pkeyopt rsa_oaep_md:sha256 -in k.bin -out NAME.key.enc
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass file:k.bin -in NAME -out NAME.enc
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import subprocess
import sys
import tempfile
from pathlib import Path

KEY_DIR = Path("/etc/tbw-digital-inbox")
KEY = KEY_DIR / "key.pem"
DONE = Path("/var/lib/tbw-once")
REMOTE = Path(sys.argv[1] if len(sys.argv) > 1 else "/var/www/thebookswanderer.com")
INBOX = REMOTE / "deploy" / "inbox"
SERVER = REMOTE / "server"


def ensure_key() -> None:
    if not KEY.is_file():
        KEY_DIR.mkdir(mode=0o700, exist_ok=True)
        os.chmod(KEY_DIR, 0o700)
        old = os.umask(0o077)
        try:
            subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:4096",
                            "-out", str(KEY)], check=True, capture_output=True)
        finally:
            os.umask(old)
        print("digital inbox: new key created")
    pub = subprocess.run(["openssl", "pkey", "-in", str(KEY), "-pubout"], check=True,
                         capture_output=True, text=True).stdout
    print("digital inbox public key:\n" + pub.strip())


def digital_dir() -> Path:
    env = SERVER / ".env"
    for line in env.read_text().splitlines() if env.is_file() else []:
        if line.startswith("DIGITAL_DIR="):
            return Path(line.split("=", 1)[1].strip().strip('"\''))
    return Path("/var/lib/tbw-digital")


def install(entry: dict) -> None:
    name, slug, sha = entry["file"], entry["slug"], entry["sha256"].lower()
    marker = DONE / f"digital-inbox-{name}-{sha[:12]}"
    if marker.exists():
        return
    enc, wrapped = INBOX / f"{name}.enc", INBOX / f"{name}.key.enc"
    if "/" in name or not enc.is_file() or not wrapped.is_file():
        print(f"digital inbox: {name}: missing or bad name, skipped")
        return
    with tempfile.TemporaryDirectory() as tmp:
        k, out = Path(tmp) / "k.bin", Path(tmp) / name
        subprocess.run(["openssl", "pkeyutl", "-decrypt", "-inkey", str(KEY), "-pkeyopt", "rsa_padding_mode:oaep",
                        "-pkeyopt", "rsa_oaep_md:sha256", "-in", str(wrapped), "-out", str(k)],
                       check=True, capture_output=True)
        subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-pass", f"file:{k}",
                        "-in", str(enc), "-out", str(out)], check=True, capture_output=True)
        got = hashlib.sha256(out.read_bytes()).hexdigest()
        if got != sha:
            print(f"digital inbox: {name}: SHA-256 mismatch, not installed")
            return
        folder = digital_dir()
        folder.mkdir(parents=True, exist_ok=True)
        www = pwd.getpwnam("www-data")
        dest = folder / name
        part = folder / f".{name}.part"
        part.write_bytes(out.read_bytes())
        os.chown(part, www.pw_uid, www.pw_gid)
        os.chmod(part, 0o640)
        os.replace(part, dest)
    print(f"digital inbox: {name}: installed ({dest.stat().st_size // 1024} KB, sha256 ok)")
    code = (
        "from database import SessionLocal\nfrom models import Product\n"
        f"db = SessionLocal(); p = db.query(Product).filter(Product.slug == {slug!r}).first()\n"
        f"assert p is not None, 'product not found'; p.digital_file = {name!r}; db.commit(); print('file linked to', p.id)\n"
    )
    run = ["runuser", "-u", "www-data", "--", ".venv/bin/python"]
    subprocess.run(run + ["-c", code], cwd=SERVER, check=True)
    subprocess.run(run + ["scripts/digital_products.py", "--apply", slug], cwd=SERVER, check=True)
    DONE.mkdir(exist_ok=True)
    marker.touch()


def main() -> None:
    ensure_key()
    manifest = INBOX / "inbox.json"
    for entry in json.loads(manifest.read_text()) if manifest.is_file() else []:
        try:
            install(entry)
        except Exception as e:  # noqa: BLE001
            print(f"digital inbox: {entry.get('file')}: failed ({type(e).__name__}), will retry next deploy")


if __name__ == "__main__":
    main()
