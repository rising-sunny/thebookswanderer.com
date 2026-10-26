from verify import load, norm
from content import NOVELS
for n in NOVELS:
    t = load(n["key"]); bad = []
    for w in n["words"] + [a for a, _ in n["cross"]]:
        if w.lower() not in t: bad.append(("word", w))
    for q, who in n["who"] + [n["crypto"]]:
        if norm(q) not in t: bad.append(("quote", q[:70]))
    print(n["key"], "OK" if not bad else bad)
for n in NOVELS:
    t = load(n["key"]); bad = []
    for w in n["words2"]:
        if w.lower() not in t: bad.append(("word2", w))
    for q, w in n["missing"] + [n["crypto2"]]:
        if norm(q) not in t: bad.append(("quote2", q[:60]))
        elif n["crypto2"][0] != q and w.lower() not in q.lower(): bad.append(("blank", w))
    for q in n["quiz"]:
        for opt in q[1:]:
            pass
    print("more", n["key"], "OK" if not bad else bad)
