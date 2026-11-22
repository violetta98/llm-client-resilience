"""Renders every task file from tasks/catalog.py and checks prompt uniformity
and neutrality. Usage: python3 tasks/generate.py  (writes tasks/<ID>/...)

Outputs per task:
  spec.md          human-readable specification (for the author's review)
  api_doc.md       the API excerpt exactly as shown to models (per language)
  signature.json   function name and signature per language, driver arguments
  expected.yaml    draft Table IV: faulted request, logical-call key, allowed outcomes per scenario
  prompts/<lang>/<C0|C1|C2>.txt
and tasks/checks.json (uniformity / neutrality checks).
"""
import json
import re
import sys
import textwrap
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import catalog as C  # noqa: E402

INIT = {"url": "URL", "id": "ID"}


def camel(n):
    a = n.split("_")
    return a[0] + "".join(x.capitalize() for x in a[1:])


def go_ident(n, exported):
    a = n.split("_")
    out = []
    for i, x in enumerate(a):
        if x in INIT and (i > 0 or exported):
            out.append(INIT[x])
        elif x.endswith("s") and x[:-1] in INIT and (i > 0 or exported):  # urls -> URLs
            out.append(INIT[x[:-1]] + "s")
        elif i == 0 and not exported:
            out.append(x)
        else:
            out.append(x.capitalize())
    return "".join(out)


def pname(lang, n):
    return {"python": n, "typescript": camel(n), "java": camel(n), "go": go_ident(n, False)}[lang]


def fname(lang, n):
    return {"python": n, "typescript": camel(n), "java": camel(n), "go": go_ident(n, True)}[lang]


TYPES = {
    "str": {"python": "str", "typescript": "string", "java": "String", "go": "string"},
    "float": {"python": "float", "typescript": "number", "java": "double", "go": "float64"},
    "list[str]": {"python": "list[str]", "typescript": "string[]", "java": "List<String>", "go": "[]string"},
    "event": {"python": "dict", "typescript": "Record<string, unknown>", "java": "Map<String, Object>", "go": "map[string]any"},
    "records": {"python": "list[dict]", "typescript": "Array<Record<string, unknown>>", "java": "List<Map<String, Object>>", "go": "[]map[string]any"},
}
RET = {
    "object": {"python": "dict", "typescript": "Record<string, unknown>", "java": "Map<String, Object>", "go": "map[string]any"},
    "objects": {"python": "list[dict]", "typescript": "Array<Record<string, unknown>>", "java": "List<Map<String, Object>>", "go": "[]map[string]any"},
    "bool": {"python": "bool", "typescript": "boolean", "java": "boolean", "go": "bool"},
    "str": {"python": "str", "typescript": "string", "java": "String", "go": "string"},
    "int": {"python": "int", "typescript": "number", "java": "int", "go": "int"},
    "none": {"python": "None", "typescript": "void", "java": "void", "go": None},
}


def signature(t, lang):
    ps = t["params"]
    fn = fname(lang, t["func"])
    r = RET[t["returns"]][lang]
    err = t["error"]
    if lang == "python":
        return f"def {fn}({', '.join(f'{pname(lang, n)}: {TYPES[ty][lang]}' for n, ty in ps)}) -> {r}"
    if lang == "typescript":
        return f"export async function {fn}({', '.join(f'{pname(lang, n)}: {TYPES[ty][lang]}' for n, ty in ps)}): Promise<{r}>"
    if lang == "java":
        thr = f" throws {err}Exception" if err else ""
        return f"public static {r} {fn}({', '.join(f'{TYPES[ty][lang]} {pname(lang, n)}' for n, ty in ps)}){thr}"
    # go: group consecutive params of the same type
    groups = []
    for n, ty in ps:
        g = TYPES[ty][lang]
        if groups and groups[-1][1] == g:
            groups[-1][0].append(pname(lang, n))
        else:
            groups.append(([pname(lang, n)], g))
    args = ", ".join(f"{', '.join(ns)} {g}" for ns, g in groups)
    if err:
        res = "error" if r is None else f"({r}, error)"
    else:
        res = r
    return f"func {fn}({args}) {res}"


def raise_text(lang, name):
    return {"python": f"Raise {name}Error", "typescript": f"Throw a {name}Error",
            "java": f"Throw a {name}Exception", "go": "Return an error"}[lang]


def subst(text, t, lang):
    text = re.sub(r"\{RAISE:(\w+)\}", lambda m: raise_text(lang, m.group(1)), text)
    text = text.replace("{ROR}", {"python": "return or raise", "typescript": "return or throw",
                                  "java": "return or throw", "go": "return"}[lang])
    text = text.replace("{NULL}", {"python": "None", "typescript": "null", "java": "null", "go": "nil"}[lang])
    text = text.replace("{FALSE}", {"python": "False", "typescript": "false", "java": "false", "go": "false"}[lang])
    text = re.sub(r"\{p:(\w+)\}", lambda m: pname(lang, m.group(1)), text)
    names = {n for n, _ in t["params"]}
    text = re.sub(r"\{(\w+)\}", lambda m: "{" + pname(lang, m.group(1)) + "}" if m.group(1) in names else m.group(0), text)
    return text


def wrap(s, indent="  "):
    return textwrap.fill(s, width=100, initial_indent=indent, subsequent_indent=indent, break_long_words=False,
                         break_on_hyphens=False)


def api_block(t, lang):
    out = []
    multi = len(t["api"]) > 1
    for ep in t["api"]:
        label = f" ({ep['label']})" if multi or ep.get("label") else ""
        out.append(f"API{label}: " + subst(ep["line"], t, lang))
        out.append(wrap(subst(ep["codes"], t, lang)))
        out.extend("  " + x for x in C.OPS)
        if ep.get("idem"):
            out.append(wrap(ep["idem"]))
    return "\n".join(out)


def task_body(t, lang):
    opener = C.OPENER[lang].format(cls=t["java_class"])
    desc = subst(" ".join(t["description"]), t, lang)
    return "\n".join([opener, "  " + signature(t, lang), textwrap.fill(desc, width=100), api_block(t, lang),
                      "Available: " + C.AVAILABLE[lang]])


def prompt(t, lang, cond):
    parts = [task_body(t, lang)]
    if cond == "C1":
        parts.append(C.C1_TEXT)
    elif cond == "C2":
        parts.append(C.C2_TEXT)
    parts.append(C.FINAL)
    return "\n".join(parts) + "\n"


def outcomes(t):
    write = t["group"] == "write" or t["id"] in ("B1", "B4")
    scen = C.SCEN_WRITE if write else C.SCEN_ALL
    err_ok = t["error"] is not None and t["group"] in ("read", "write", "background")
    if t["id"] in ("H1",):
        err_ok = False  # faults hit the recommendations only: the profile must still be returned
    base = ["correct"] + (["degraded"] if t["degraded"] else []) + (["error"] if err_ok else [])
    out = {"S0": ["correct"]}
    for s in scen[1:]:
        out[s] = list(base)
    if t["group"] == "background" and "S7" in out:
        out["S7"] = ["error"]  # a 30 s outage cannot be outlasted within a 30 s limit
    if t["group"] == "handler" and "S7" in out:
        out["S7"] = ["degraded"]
    if (t["id"] == "W2" or t.get("s8_error_only")) and "S8" in out:
        out["S8"] = ["error"]  # the outcome is unknown: an error, not a second SMS
    return scen, out


def expected(t):
    scen, outc = outcomes(t)
    return {
        "task": t["id"], "title": t["title"], "group": t["group"], "status": STATUS,
        "time_limit_s": t["time_limit_s"], "overrun_threshold_s": None if t["time_limit_s"] is None else t["time_limit_s"] + 0.25,
        "dependencies": {d: {"name": n, "port": {"A": 9001, "B": 9002, "C": 9003}[d]} for d, n in t["deps"].items()},
        "fault_dependency": t["fault_dep"], "faulted_request": t["faulted_request"], "logical_call_key": t["logical_key"],
        "connection_faults_scope": "S1, S2, S9: every connection to the faulted dependency from the start of the run",
        "state_changing": "S8" in scen, "scenarios": scen,
        "correct_result": t["correct"], "degraded_result": t["degraded"],
        "effects_constraint": t.get("effects"),
        "allowed_outcomes": outc,
        "silent_failure": "any returned value that is neither the correct nor the allowed degraded result (Table V)",
        "table_iv": t["table_iv"],
        "args": {"warmup": t["warmup"], "single": t["single"], "s7": t["s7"]},
        **({"unsafe_effect": t["unsafe_effect"]} if t.get("unsafe_effect") else {}),
    }


def sig_json(t):
    d = {"task": t["id"], "deps": list(t["deps"]), "status": STATUS,
         "warmup_args": t["warmup"], "single_args": t["single"], "s7_args": t["s7"]}
    for lang in C.LANGS:
        d[lang] = {"function": fname(lang, t["func"]), "signature": signature(t, lang)}
        if lang == "java":
            d[lang]["class"] = t["java_class"]
    return d


def spec_md(t):
    e = expected(t)
    L = [f"# {t['id']} — {t['title']}", "", f"Status: **{STATUS}.** Generated from `tasks/{'pilot_catalog' if PILOT else 'catalog'}.py`.", "",
         f"- Group: {t['group']}; method: {t['method']}; context: {t['context']}",
         f"- Time limit: {str(t['time_limit_s']) + ' s' if t['time_limit_s'] else 'none stated'}",
         f"- Dependencies: " + ", ".join(f"{d} = {n} (port {e['dependencies'][d]['port']})" for d, n in t["deps"].items()),
         f"- Faulted dependency: {t['fault_dep']}; faulted request (S3–S8): {t['faulted_request']}",
         f"- Logical-call key: {t['logical_key']}", "",
         "## Prompt body (Python, C0)", "", "```", prompt(t, "python", "C0").rstrip(), "```", "",
         "## Signatures", ""]
    for lang in C.LANGS:
        L.append(f"- {lang}: `{signature(t, lang)}`" + (f" (class `{t['java_class']}`)" if lang == "java" else ""))
    L += ["", "## Mock behavior (normal, S0)", ""] + [f"- {m}" for m in t["mock"]]
    L += ["", "## Correct behavior (draft Table IV)", "", f"{t['table_iv']}", "",
          f"- Correct result (S0, single call): {json.dumps(t['correct'], ensure_ascii=False)}",
          f"- Degraded result: {json.dumps(t['degraded'], ensure_ascii=False) if t['degraded'] else '— (none allowed)'}",
          f"- Effects constraint: {t.get('effects') or '—'}", "", "| Scenario | Allowed outcomes |", "|---|---|"]
    for s, a in e["allowed_outcomes"].items():
        L.append(f"| {s} | {', '.join(a)} |")
    L += ["", "Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately."]
    if t.get("notes"):
        L += ["", "## Notes"] + [f"- {n}" for n in t["notes"]]
    return "\n".join(L) + "\n"


BANNED = [r"time ?outs?\b", r"\btimed? out\b", r"\bretr(y|ies|ied|ying)\b(?!-after)", r"back ?off", r"jitter", r"resilien",
          r"\brobust", r"circuit", r"exponential", r"production"]


STATUS = "frozen with protocol v1 (E6)"
PILOT = False


def main():
    global STATUS, PILOT
    tasks, root = C.TASKS, HERE
    if "--pilot" in sys.argv[1:]:
        import pilot_catalog as P
        tasks, root, PILOT = P.PILOT_TASKS, HERE.parent / "pilot" / "tasks", True
        STATUS = "PILOT task (outside the benchmark; brief E5)"
    checks = {"ops_lines_identical": True, "c0_neutral": [], "c1_neutral": [], "prompt_counts": 0}
    for t in tasks:
        d = root / t["id"]
        (d / "prompts").mkdir(parents=True, exist_ok=True)
        (d / "spec.md").write_text(spec_md(t))
        (d / "signature.json").write_text(json.dumps(sig_json(t), indent=1, ensure_ascii=False) + "\n")
        (d / "expected.yaml").write_text(yaml.safe_dump(expected(t), sort_keys=False, allow_unicode=True, width=120))
        api = ["# API documentation excerpt shown to the models", ""]
        for lang in C.LANGS:
            api += [f"## {lang}", "", "```", api_block(t, lang), "```", ""]
        (d / "api_doc.md").write_text("\n".join(api))
        for lang in C.LANGS:
            (d / "prompts" / lang).mkdir(parents=True, exist_ok=True)
            for cond in ("C0", "C1", "C2"):
                p = prompt(t, lang, cond)
                (d / "prompts" / lang / f"{cond}.txt").write_text(p)
                checks["prompt_counts"] += 1
                n_eps = len(t["api"])
                if p.count("\n  " + C.OPS[0] + "\n  " + C.OPS[1] + "\n") != n_eps:
                    checks["ops_lines_identical"] = False
                # The offered-library line names retry libraries by design (draft IV-B); it is
                # excluded from the neutrality check, as are the header names Retry-After and
                # Idempotency-Key, which the operational lines contain by design.
                body = "\n".join(x for x in p.splitlines() if not x.startswith("Available: "))
                body = body.replace("Retry-After", "").replace("Idempotency-Key", "")
                if cond in ("C0", "C1"):
                    for b in BANNED:
                        txt = body.replace(C.C1_TEXT, "") if cond == "C1" else body
                        if re.search(b, txt, re.I):
                            checks[f"{cond.lower()}_neutral"].append(f"{t['id']}/{lang}: /{b}/")
                if not p.rstrip().endswith(C.FINAL):
                    checks.setdefault("bad_final_line", []).append(f"{t['id']}/{lang}/{cond}")
    # the task part is identical across conditions
    for t in tasks:
        for lang in C.LANGS:
            ps = [(root / t["id"] / "prompts" / lang / f"{c}.txt").read_text() for c in ("C0", "C1", "C2")]
            if not all(x.startswith(task_body(t, lang)) for x in ps):
                checks.setdefault("task_part_differs", []).append(f"{t['id']}/{lang}")
    (root / "checks.json").write_text(json.dumps(checks, indent=1) + "\n")
    print(json.dumps(checks, indent=1))


if __name__ == "__main__":
    main()
