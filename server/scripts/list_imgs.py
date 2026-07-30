import json
import re
from pathlib import Path

d = json.loads(Path(__file__).resolve().parents[1].joinpath("data/CJYD2138789.json").read_text(encoding="utf-8"))
print("SET")
for u in d.get("productImageSet") or []:
    print(u)
print("DESC")
for m in re.finditer(r'src="(https://[^"]+)"', d.get("description") or ""):
    print(m.group(1))
print("VARIANT")
for v in d.get("variants") or []:
    print(v.get("variantKey"), "|", v.get("variantImage"))
