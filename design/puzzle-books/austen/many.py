import sys, re
from verify import norm
k = sys.argv[1]
raw = re.sub(r"\s+", " ", open(f"txt/{k}.txt", encoding="utf-8").read().replace("_", ""))
low = raw.lower().replace("’", "'").replace("‘", "'")
for frag in sys.argv[2:]:
    i = low.find(frag.lower())
    print("##", frag, "->", "NOT FOUND" if i < 0 else raw[max(0, i - 160): i + 200])
