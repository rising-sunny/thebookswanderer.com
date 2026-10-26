import re, sys
def norm(s):
    s = s.replace("_", "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).lower()
def load(k): return norm(open(f"txt/{k}.txt", encoding="utf-8").read())
def ctx(k, q, n=260):
    t = load(k); i = t.find(norm(q))
    return None if i < 0 else t[max(0, i - n): i + len(q) + 120]
if __name__ == "__main__":
    k, q = sys.argv[1], sys.argv[2]
    print(ctx(k, q) or "NOT FOUND")
