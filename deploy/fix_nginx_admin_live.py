#!/usr/bin/env python3
"""Insert /admin/ reverse-proxy location into TBW nginx site config."""
from pathlib import Path
import subprocess
import sys

CONF = Path("/etc/nginx/sites-available/thebookswanderer.com")

SNIPPET = """
    # Admin live dashboard (auth cookie + SSE stream)
    location /admin/ {
        proxy_pass http://127.0.0.1:8010;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
"""


def main() -> int:
    text = CONF.read_text()
    if "location /admin/" in text:
        print("admin location already present")
    else:
        marker = "location /api/"
        idx = text.find(marker)
        if idx < 0:
            print("no /api/ location found", file=sys.stderr)
            return 1
        sub = text[idx:]
        depth = 0
        end = None
        for i, ch in enumerate(sub):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            print("could not find end of /api/ block", file=sys.stderr)
            return 1
        insert_at = idx + end + 1
        text = text[:insert_at] + "\n" + SNIPPET + text[insert_at:]
        CONF.write_text(text)
        print("inserted admin location")

    r = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    print(r.stderr or r.stdout)
    if r.returncode != 0:
        return r.returncode
    subprocess.check_call(["systemctl", "reload", "nginx"])
    print("nginx reloaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
