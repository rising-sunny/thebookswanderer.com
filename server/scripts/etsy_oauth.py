#!/usr/bin/env python3
"""Connect the store to Etsy once (OAuth with PKCE) for the supplier API proxy.

Run on the VPS as the store user, after adding ETSY_API_KEY to .env and
ETSY_REDIRECT_URI to the Etsy app's callback URLs:

  sudo -u www-data .venv/bin/python scripts/etsy_oauth.py

Open the printed link, approve, then paste the full address the browser
lands on (the page itself may show an error). Prints no secrets.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402

from services import etsy  # noqa: E402

SCOPES = "listings_r listings_w listings_d shops_r shops_w transactions_r transactions_w profile_r"
redirect = (os.getenv("ETSY_REDIRECT_URI") or "https://thebookswanderer.com/etsy-oauth").strip()
if not etsy.client_id():
    raise SystemExit("ETSY_API_KEY is missing from .env")

verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
state = secrets.token_urlsafe(16)
print("1. Open and approve:\n")
print("https://www.etsy.com/oauth/connect?" + urlencode({
    "response_type": "code", "client_id": etsy.client_id(), "redirect_uri": redirect,
    "scope": SCOPES, "state": state, "code_challenge": challenge,
    "code_challenge_method": "S256",
}))
query = parse_qs(urlparse(input("\n2. Paste the address you land on: ").strip()).query)
if query.get("state", [""])[0] != state or not query.get("code"):
    raise SystemExit("No code, or the state does not match. Nothing saved.")

response = httpx.post(etsy.TOKEN_URL, timeout=20, data={
    "grant_type": "authorization_code", "client_id": etsy.client_id(),
    "redirect_uri": redirect, "code": query["code"][0], "code_verifier": verifier,
})
if response.status_code != 200:
    raise SystemExit(f"Token exchange failed: HTTP {response.status_code}")
etsy.save_token(response.json())
print(f"Connected. Token saved to {etsy.token_file()} (mode 600).")
