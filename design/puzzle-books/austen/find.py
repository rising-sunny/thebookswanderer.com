import re, sys
k, frag = sys.argv[1], sys.argv[2]
raw = re.sub(r"\s+", " ", open(f"txt/{k}.txt", encoding="utf-8").read().replace("_", ""))
low = raw.lower().replace("’", "'").replace("‘", "'")
i = low.find(frag.lower())
while i >= 0:
    print("...", raw[max(0, i - 200): i + 260], "\n")
    i = low.find(frag.lower(), i + 1)
    if i > 0 and len(sys.argv) < 4: break
