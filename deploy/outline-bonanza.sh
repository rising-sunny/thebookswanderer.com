#!/bin/bash
# One-time outline of the existing Bonanza bridge code, without copying it into the deploy log:
# functions (first docstring line), HTTP routes, Bonanza API call names, hosts contacted.
# String literals are only shown when they look like a route, an API call name or a host.
set -u
BRIDGE=/opt/mathrelaxing-bridge

python3 - "$BRIDGE" <<'PY'
import ast, re, sys
from pathlib import Path

root = Path(sys.argv[1])
files = sorted(root.glob("bonanza_*.py")) + [root / "server.py"]
route_re = re.compile(r"^/[A-Za-z0-9_./{}:<>-]*$")
call_re = re.compile(r"^(add|get|revise|end|relist|set|complete|fetch|update|delete|upload)[A-Z][A-Za-z]{2,40}$")
for f in files:
    if not f.is_file():
        continue
    try:
        tree = ast.parse(f.read_text(errors="replace"))
    except SyntaxError as e:
        print(f"== {f.name}: syntax error {e.lineno}"); continue
    lines = len(f.read_text(errors="replace").splitlines())
    doc = (ast.get_docstring(tree) or "").strip().splitlines()
    print(f"== {f.name} ({lines} lines){': ' + doc[0][:120] if doc else ''}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            d = (ast.get_docstring(node) or "").strip().splitlines()
            args = ", ".join(a.arg for a in node.args.args)
            deco = []
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and dec.args and isinstance(dec.args[0], ast.Constant) \
                        and isinstance(dec.args[0].value, str) and route_re.match(dec.args[0].value):
                    fn = dec.func.attr if isinstance(dec.func, ast.Attribute) else getattr(dec.func, "id", "?")
                    deco.append(f"{fn.upper()} {dec.args[0].value}")
            print(f"  def {node.name}({args})" + (f"  [{'; '.join(deco)}]" if deco else "") + (f"  # {d[0][:100]}" if d else ""))
    routes, calls, hosts = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.strip()
            if route_re.match(s) and 1 < len(s) < 80 and s.count("/") >= 1 and not s.startswith(("/etc", "/var", "/opt", "/root", "/usr", "/tmp")):
                routes.add(s)
            if call_re.match(s):
                calls.add(s)
            for h in re.findall(r"https?://([A-Za-z0-9.-]+)", s):
                hosts.add(h)
    if routes: print("  paths:", ", ".join(sorted(routes)[:60]))
    if calls:  print("  api calls:", ", ".join(sorted(calls)))
    if hosts:  print("  hosts:", ", ".join(sorted(hosts)))
PY

echo "== nginx locations (codex-api.conf)"
grep -nE "^[ \t]*location" /etc/nginx/conf.d/codex-api.conf 2>/dev/null | sed -E 's/[ \t]*\{.*$//; s/^/  /'
echo "== state directory"
ls -la /var/lib/mathrelaxing-bonanza-api 2>/dev/null | awk 'NR>1 {print "  " $1, $5, $6, $7, $8, $9}' | head -30
echo "== done"
