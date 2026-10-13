"""Prepare an encrypted transport for private print files; no product writes."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from services.digital import digital_dir


def main():
    folder = digital_dir() / '.release-private'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    key = folder / 'lost-manuscript.pem'
    cert = ROOT.parent / 'assets/products/the-lost-manuscript/release-certificate.pem'
    cert.parent.mkdir(parents=True, exist_ok=True)
    if not key.exists():
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '30',
                        '-subj', '/CN=The Books Wanderer print-file transport'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(key, 0o600)
    elif not cert.exists():
        subprocess.run(['openssl', 'req', '-new', '-x509', '-key', str(key),
                        '-out', str(cert), '-days', '30',
                        '-subj', '/CN=The Books Wanderer print-file transport'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('Public encryption certificate: /assets/products/the-lost-manuscript/release-certificate.pem')
    print('Private key stays on the server. No product activated and no print job created.')


if __name__ == '__main__':
    main()
