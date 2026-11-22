"""Prepare step for Python solutions (no network): syntax check and detection
of imports of modules that are not installed (missing_dependency).
Input /src/solution.py; output /out/solution.py and /out/prepare.json."""
import ast
import importlib.util
import json
import shutil
import sys
import time

t0 = time.monotonic()
out = {"schema": "prepare/1", "lang": "python", "tool": f"python {sys.version.split()[0]} ast"}


def finish(category, **kw):
    out.update(category=category, duration_s=time.monotonic() - t0, **kw)
    json.dump(out, open("/out/prepare.json", "w"), indent=1)
    sys.exit(0)


src = open("/src/solution.py", encoding="utf-8", errors="replace").read()
try:
    tree = ast.parse(src)
except SyntaxError as e:
    finish("compile_error", errors=[f"{e.lineno}:{e.offset} {e.msg}"])
mods = set()
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        mods.update(a.name.split(".")[0] for a in n.names)
    elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
        mods.add(n.module.split(".")[0])
missing = sorted(m for m in mods if importlib.util.find_spec(m) is None)
shutil.copy("/src/solution.py", "/out/solution.py")
out["imports"] = sorted(mods)
if missing:
    finish("missing_dependency", missing=missing)
finish("ok")
