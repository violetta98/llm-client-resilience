"""Renders the four confirmatory tasks (tasks/confirm_catalog.py) into tasks/<ID>/.

Usage: python3 tasks/generate_confirm.py

It imports tasks/generate.py and calls ITS functions (signature, prompt, api_block,
expected, sig_json, spec_md) unchanged, so the prompts are produced by exactly the
same templates as the 16 benchmark tasks; tasks/generate.py, tasks/catalog.py and
every file of the existing tasks are neither changed nor rewritten. Only the status
line and the name of the source catalog differ. The uniformity / neutrality checks
of tasks/generate.py are repeated for the new prompts and written to
tasks/confirm_checks.json (tasks/checks.json is left alone).
"""
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as G  # noqa: E402  (tasks/generate.py; main() is not called)
import confirm_catalog as CC  # noqa: E402

C = G.C  # tasks/catalog.py: operational lines, offered libraries, condition texts
NEW_IDS = {"R6", "W5", "B5", "H4"}


def main():
    G.STATUS = CC.STATUS
    G.PILOT = False
    tasks = CC.CONFIRM_TASKS
    assert {t["id"] for t in tasks} == NEW_IDS
    bench = {t["id"] for t in C.TASKS}
    checks = {"ops_lines_identical": True, "c0_neutral": [], "c1_neutral": [], "prompt_counts": 0}
    for t in tasks:
        assert t["id"] not in bench, t["id"]
        d = HERE / t["id"]
        (d / "prompts").mkdir(parents=True, exist_ok=True)
        spec = G.spec_md(t).replace("Generated from `tasks/catalog.py`.", "Generated from `tasks/confirm_catalog.py` (tasks/generate_confirm.py).")
        (d / "spec.md").write_text(spec)
        (d / "signature.json").write_text(json.dumps(G.sig_json(t), indent=1, ensure_ascii=False) + "\n")
        (d / "expected.yaml").write_text(yaml.safe_dump(G.expected(t), sort_keys=False, allow_unicode=True, width=120))
        api = ["# API documentation excerpt shown to the models", ""]
        for lang in C.LANGS:
            api += [f"## {lang}", "", "```", G.api_block(t, lang), "```", ""]
        (d / "api_doc.md").write_text("\n".join(api))
        for lang in C.LANGS:
            (d / "prompts" / lang).mkdir(parents=True, exist_ok=True)
            for cond in ("C0", "C1", "C2"):
                p = G.prompt(t, lang, cond)
                (d / "prompts" / lang / f"{cond}.txt").write_text(p)
                checks["prompt_counts"] += 1
                if p.count("\n  " + C.OPS[0] + "\n  " + C.OPS[1] + "\n") != len(t["api"]):
                    checks["ops_lines_identical"] = False
                body = "\n".join(x for x in p.splitlines() if not x.startswith("Available: "))
                body = body.replace("Retry-After", "").replace("Idempotency-Key", "")
                if cond in ("C0", "C1"):
                    for b in G.BANNED:
                        txt = body.replace(C.C1_TEXT, "") if cond == "C1" else body
                        if re.search(b, txt, re.I):
                            checks[f"{cond.lower()}_neutral"].append(f"{t['id']}/{lang}: /{b}/")
                if not p.rstrip().endswith(C.FINAL):
                    checks.setdefault("bad_final_line", []).append(f"{t['id']}/{lang}/{cond}")
                if ("Available: " + C.AVAILABLE[lang] + "\n") not in p:
                    checks.setdefault("available_line_differs", []).append(f"{t['id']}/{lang}/{cond}")
    for t in tasks:
        for lang in C.LANGS:
            ps = [(HERE / t["id"] / "prompts" / lang / f"{c}.txt").read_text() for c in ("C0", "C1", "C2")]
            if not all(x.startswith(G.task_body(t, lang)) for x in ps):
                checks.setdefault("task_part_differs", []).append(f"{t['id']}/{lang}")
    (HERE / "confirm_checks.json").write_text(json.dumps(checks, indent=1) + "\n")
    print(json.dumps(checks, indent=1))


if __name__ == "__main__":
    main()
