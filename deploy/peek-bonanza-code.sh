#!/bin/bash
# One-time: print the few functions that define how to talk to the Bonanza gateway socket
# (message format, validation rules). Credentials live in systemd credentials, not in code;
# still, every string literal that looks like a key or token is replaced before printing.
set -u
python3 - <<'PY'
import ast, re
from pathlib import Path

B = Path("/opt/mathrelaxing-bridge")
WANT = {
    "bonanza_api_addon.py": None,                       # whole file (39 lines)
    "bonanza_gateway.py": {"validate", "validate_headers", "validate_payload", "process", "handle", "forward"},
}
TOKENISH = re.compile(r"(['\"])([A-Za-z0-9_\-+/=.]{24,})\1")
SECRETISH = re.compile(r"(?i)(token|secret|password|cert|dev_id|api_key|authorization)(['\"]?\s*[:=]\s*)(['\"])[^'\"]{6,}\3")

def scrub(text):
    text = TOKENISH.sub(lambda m: m.group(1) + "<redacted>" + m.group(1), text)
    return SECRETISH.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + "<redacted>" + m.group(3), text)

for name, funcs in WANT.items():
    f = B / name
    if not f.is_file():
        print(f"== {name}: missing"); continue
    src = f.read_text(errors="replace")
    print(f"== {name}")
    if funcs is None:
        print(scrub(src)); continue
    tree = ast.parse(src)
    lines = src.splitlines()
    # module-level constants that hold limits or allow-lists (not long strings)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            seg = ast.get_source_segment(src, node) or ""
            if len(seg) < 1500:
                print(scrub(seg))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in funcs:
            print(f"-- {node.name} (lines {node.lineno}-{node.end_lineno})")
            print(scrub("\n".join(lines[node.lineno - 1:node.end_lineno])))
PY
echo "== socket"
ls -la /run/mathrelaxing-bonanza-api/ 2>/dev/null | awk 'NR>1 {print "  " $1, $3, $4, $9}'
echo "== done"
