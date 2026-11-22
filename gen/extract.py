"""Fixed code-extraction rule (brief 3.7; draft Section V-C).

1. The LAST non-empty fenced block whose info string names the target
   language (python: python, py, python3; typescript: typescript, ts;
   java: java; go: go, golang). Case-insensitive; ``` and ~~~ fences.
   A block with only whitespace is not code (pilot finding, reports/pilot.md).
2. Otherwise the whole response, if it contains no fence and parses:
   Python - ast.parse; other languages - accepted as an "unfenced candidate"
   whose prepare step (compile/transpile) decides: a compile error of an
   unfenced candidate is reported as no_code, not as compile_error.
3. Otherwise no_code.
"""
from __future__ import annotations

import ast
import re

TAGS = {"python": {"python", "py", "python3"}, "typescript": {"typescript", "ts"}, "java": {"java"},
        "go": {"go", "golang"}}
EXT = {"python": "py", "typescript": "ts", "java": "java", "go": "go"}
FENCE = re.compile(r"^(?P<ind>[ \t]{0,3})(?P<f>`{3,}|~{3,})[ \t]*(?P<info>[^\n`]*)\n(?P<code>.*?)^[ \t]{0,3}(?P=f)[`~]*[ \t]*$",
                   re.M | re.S)


def blocks(text):
    out = []
    for m in FENCE.finditer(text):
        info = m.group("info").strip().split()
        out.append({"lang": info[0].lower().lstrip("{.") if info else "", "code": m.group("code"),
                    "start": m.start()})
    return out


def extract(text, lang):
    """Returns {"status": fenced|unfenced|no_code, "code": str|None, "n_blocks": int, "n_target_blocks": int}."""
    text = (text or "").replace("\r\n", "\n")
    bs = blocks(text)
    target = [b for b in bs if b["lang"] in TAGS[lang]]
    res = {"n_blocks": len(bs), "n_target_blocks": len(target)}
    nonempty = [b for b in target if b["code"].strip()]
    if nonempty:
        return {"status": "fenced", "code": nonempty[-1]["code"], **res}
    if target:
        return {"status": "no_code", "code": None, **res}
    if "```" not in text and "~~~" not in text and text.strip():
        if lang == "python":
            try:
                ast.parse(text)
            except SyntaxError:
                return {"status": "no_code", "code": None, **res}
        return {"status": "unfenced", "code": text, **res}
    return {"status": "no_code", "code": None, **res}
