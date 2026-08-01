#!/usr/bin/env python3
"""Insert/fix product.html SSR proxy blocks in the live nginx site config."""
from __future__ import annotations

import re
from pathlib import Path

CONF = Path("/etc/nginx/sites-enabled/thebookswanderer.com")
SNIPPET = Path("/tmp/nginx-product-ssr-snippet.conf")


def main() -> None:
    text = CONF.read_text(encoding="utf-8")
    # Drop any previous SSR blocks (including broken PowerShell-expanded ones)
    text = re.sub(
        r"\n[ \t]*# Product PDP SSR[\s\S]*?(?=\n[ \t]*location / \{)",
        "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"\n[ \t]*location = /product\.html \{[\s\S]*?\n[ \t]*\}\n"
        r"[ \t]*location /products/ \{[\s\S]*?\n[ \t]*\}\n",
        "\n",
        text,
        count=1,
    )
    snippet = SNIPPET.read_text(encoding="utf-8").rstrip() + "\n\n"
    idx = text.find("location / {")
    if idx < 0:
        raise SystemExit("location / { not found")
    text = text[:idx] + snippet + text[idx:]
    CONF.write_text(text, encoding="utf-8")
    print("OK wrote", CONF)
    # sanity
    body = CONF.read_text(encoding="utf-8")
    assert "location = /product.html" in body
    assert "$host" in body
    assert "InternalHost" not in body
    print("sanity ok")


if __name__ == "__main__":
    main()
