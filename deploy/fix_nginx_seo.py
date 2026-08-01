#!/usr/bin/env python3
"""Install SEO SSR locations + force www → apex 301 on the live nginx site."""
from __future__ import annotations

import re
from pathlib import Path

CONF = Path("/etc/nginx/sites-enabled/thebookswanderer.com")
SNIPPET = Path("/tmp/nginx-seo-locations.conf")


def main() -> None:
    text = CONF.read_text(encoding="utf-8")

    # Remove prior Product PDP / SEO SSR blocks we may have inserted
    text = re.sub(
        r"\n[ \t]*# (?:Product PDP SSR|--- SEO SSR)[\s\S]*?(?=\n[ \t]*location / \{)",
        "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"\n[ \t]*location = /product\.html \{[\s\S]*?\n[ \t]*\}\n"
        r"(?:[ \t]*location /products/ \{[\s\S]*?\n[ \t]*\}\n)?",
        "\n",
        text,
    )
    text = re.sub(
        r"\n[ \t]*location = / \{\n[\s\S]*?\n[ \t]*\}\n"
        r"[ \t]*location = /index\.html \{[\s\S]*?\n[ \t]*\}\n"
        r"[ \t]*location = /product\.html \{[\s\S]*?\n[ \t]*\}\n"
        r"[ \t]*location = /pick\.html \{[\s\S]*?\n[ \t]*\}\n"
        r"[ \t]*location /products/ \{[\s\S]*?\n[ \t]*\}\n",
        "\n",
        text,
    )

    snippet = SNIPPET.read_text(encoding="utf-8").rstrip() + "\n\n"
    idx = text.find("location / {")
    if idx < 0:
        raise SystemExit("location / { not found")
    text = text[:idx] + snippet + text[idx:]

    # www → apex 301 inside the SSL server block (prefer over serving duplicate 200)
    # Certbot block often returns 301 on :80 only; ensure www host redirects on 443.
    if "if ($host = www.thebookswanderer.com)" not in text.split("listen 443")[0]:
        # Insert www redirect at top of first server block body
        m = re.search(r"(server_name thebookswanderer\.com www\.thebookswanderer\.com;\s*)", text)
        if m and "return 301 https://thebookswanderer.com" not in text[: m.end() + 400]:
            inject = (
                m.group(1)
                + "\n    # Prefer apex host for SEO (avoid www duplicate)\n"
                + "    if ($host = www.thebookswanderer.com) {\n"
                + "        return 301 https://thebookswanderer.com$request_uri;\n"
                + "    }\n"
            )
            text = text[: m.start()] + inject + text[m.end() :]

    CONF.write_text(text, encoding="utf-8")
    body = CONF.read_text(encoding="utf-8")
    assert "location = /pick.html" in body
    assert "location = /product.html" in body
    assert "$host" in body
    assert "InternalHost" not in body
    print("OK", CONF)


if __name__ == "__main__":
    main()
