#!/usr/bin/env python3
"""One-time, read-only: why has an Etsy book order not reached Lulu yet?

Looks at the Etsy -> Lulu worker under /opt/etsy_lulu_fulfill: how it is scheduled, when it last
ran, and every record that mentions the listing or the receipt (JSON files, SQLite rows, log lines).
Personal data never reaches the output: keys that name a person or an address are dropped and
emails, street lines and long numbers are masked in free text.
"""
import json
import re
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path("/opt/etsy_lulu_fulfill")
IDS = ("4603381326", "4220948340", "TBW-JANE-AUSTEN-PUZZLE-BOOK")
PII_KEY = re.compile(r"(?i)(name|address|street|line_?\d|first_line|second_line|city|zip|post|email|phone|buyer|recipient|customer|tax_id|message)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
STREET = re.compile(r"\b\d{1,6}\s+[A-Za-z][\w .'-]{1,40}\b(street|st|avenue|ave|drive|dr|road|rd|lane|ln|blvd|way|court|ct|place|pl)\b", re.I)
CAPNAME = re.compile(r"\b[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+){1,3}\b")
LONGNUM = re.compile(r"\b(?!(?:4603381326|4220948340)\b)\d{5,}\b")


def mask(text):
    text = EMAIL.sub("<email>", text)
    text = STREET.sub("<street>", text)
    text = CAPNAME.sub("<name>", text)
    return LONGNUM.sub("<n>", text)


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not PII_KEY.search(str(k))}
    if isinstance(value, list):
        return [clean(v) for v in value[:20]]
    return mask(value) if isinstance(value, str) else value


def find(obj, path=""):
    """yield (path, dict) for dicts that mention one of IDS"""
    if isinstance(obj, dict):
        if any(i in json.dumps(obj) for i in IDS) and not any(isinstance(v, (dict, list)) and any(i in json.dumps(v) for i in IDS) for v in obj.values()):
            yield path, obj
        for k, v in obj.items():
            yield from find(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for n, v in enumerate(obj):
            yield from find(v, f"{path}[{n}]")


def run(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"({type(exc).__name__})"


print("== schedule")
print(mask(run("grep -rl etsy_lulu /etc/cron.d /var/spool/cron 2>/dev/null | head -5")))
print(mask(run("grep -rh etsy_lulu /etc/cron.d /var/spool/cron/crontabs 2>/dev/null | head -5")))
print(run("systemctl list-timers --all 2>/dev/null | grep -i lulu | head -5"))
print("== files (names, sizes, modified)")
print(run(f"find {ROOT} -maxdepth 3 -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -printf '%TY-%Tm-%Td %TH:%TM  %8s  %P\\n' 2>/dev/null | sort -r | head -40"))
print("== records mentioning the listing, SKU or receipt")
for f in sorted(ROOT.rglob("*")):
    if not f.is_file() or "__pycache__" in f.parts or f.stat().st_size > 20_000_000:
        continue
    if f.suffix == ".json":
        try:
            data = json.loads(f.read_text(errors="replace"))
        except ValueError:
            continue
        for path, d in list(find(data))[:10]:
            print(f"{f.relative_to(ROOT)}{path}: {json.dumps(clean(d), ensure_ascii=False)[:700]}")
    elif f.suffix in (".db", ".sqlite", ".sqlite3"):
        try:
            con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            for (table,) in con.execute("select name from sqlite_master where type='table'"):
                cols = [c[1] for c in con.execute(f"pragma table_info('{table}')")]
                for row in con.execute(f"select * from '{table}'"):
                    text = json.dumps(row, default=str)
                    if any(i in text for i in IDS):
                        rec = clean(dict(zip(cols, row)))
                        for k, v in list(rec.items()):
                            if isinstance(v, str) and v.startswith("{"):
                                try:
                                    rec[k] = clean(json.loads(v))
                                except ValueError:
                                    pass
                        print(f"{f.relative_to(ROOT)}:{table}: {json.dumps(rec, ensure_ascii=False, default=str)[:900]}")
            con.close()
        except sqlite3.Error as exc:
            print(f"{f.relative_to(ROOT)}: sqlite {exc}")
    elif f.suffix in (".log", ".txt") or "log" in f.name:
        lines = f.read_text(errors="replace").splitlines()
        hits = [l for l in lines if any(i in l for i in IDS)]
        print(f"{f.relative_to(ROOT)}: {len(lines)} lines, last: {mask(lines[-1])[:200] if lines else '-'}")
        for l in hits[-15:]:
            print("   ", mask(l)[:300])
for log in ["/var/log/etsy_lulu_fulfill.log", "/var/log/etsy-lulu.log"] + run("ls /var/log | grep -i lulu").split():
    p = Path(log if log.startswith("/") else "/var/log/" + log)
    if p.is_file():
        lines = p.read_text(errors="replace").splitlines()
        print(f"== {p}: {len(lines)} lines")
        for l in lines[-12:]:
            print("   ", mask(l)[:300])
        for l in [l for l in lines if any(i in l for i in IDS)][-10:]:
            print("  *", mask(l)[:300])
print("== done")
