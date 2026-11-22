"""End-to-end self-test of the generation -> extraction -> prepare -> run ->
measures pipeline WITHOUT any model: the pilot references are wrapped in
model-like responses and written as generations of a fake model, plus edge
cases for the extraction rule and the prepare categories.

Usage: python3 tests/integration/e5_selftest.py [--run dev/e5-selftest-<stamp>]
then:  python3 runner/run_generated.py --run <same>
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "gen"))
sys.path.insert(0, str(REPO / "runner"))
import extract as X  # noqa: E402
import orchestrator as o  # noqa: E402

TAG = {"python": "python", "go": "go"}


def write(base, model, task, lang, sample, text):
    d = base / "generations" / "C0" / model / task / lang / str(sample)
    d.mkdir(parents=True, exist_ok=True)
    ex = X.extract(text, lang)
    if ex["code"] is not None:
        (d / f"solution.{X.EXT[lang]}").write_text(ex["code"])
    (d / "response.json").write_text(json.dumps({"choices": [{"message": {"content": text}}], "model": "selftest"}))
    (d / "meta.json").write_text(json.dumps({"status": "ok", "model_id": model, "input_tokens": None, "output_tokens": None,
                                             "extraction": {k: v for k, v in ex.items() if k != "code"}}))
    return ex["status"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=f"dev/e5-selftest-{o.new_run_id()}")
    a = ap.parse_args()
    base = o.DATA / a.run
    idx = json.loads((REPO / "pilot" / "references" / "index.json").read_text())
    exp = {}
    for p in idx:
        src = (REPO / p["path"]).read_text()
        st = write(base, "reference", p["task"], p["lang"], 1, f"Here is the code:\n\n```{TAG[p['lang']]}\n{src}```\n")
        exp[f"reference/{p['task']}/{p['lang']}/1"] = ("ok", st)
    exp["edge/P1/python/1"] = ("no_code", write(base, "edge", "P1", "python", 1, "I cannot write this code."))
    exp["edge/P1/go/1"] = ("no_code", write(base, "edge", "P1", "go", 1, "Use net/http and call the endpoint."))
    exp["edge/P2/python/1"] = ("missing_dependency", write(
        base, "edge", "P2", "python", 1, "```python\nimport not_installed_pkg\n\n"
        "def add_ticket_comment(base_url: str, ticket_id: str, text: str) -> str:\n    return ''\n```\n"))
    # a program without any timeout: exercises the 330 s repetitions (S2-S4 do not return)
    exp["edge/P1/python/2"] = ("ok", write(
        base, "edge", "P1", "python", 2, "```python\nimport json, urllib.request\n\n"
        "class RateError(Exception):\n    pass\n\n"
        "def get_exchange_rate(base_url: str, base_currency: str, quote_currency: str) -> dict:\n"
        "    try:\n        with urllib.request.urlopen(f\"{base_url}/v1/rates/{base_currency}/{quote_currency}\") as r:\n"
        "            return json.load(r)\n    except OSError as e:\n        raise RateError(str(e)) from e\n```\n"))
    print(json.dumps({"run": a.run, "expected_categories": exp}, indent=1))
    (base / "selftest_expected.json").write_text(json.dumps({k: v[0] for k, v in exp.items()}, indent=1))


if __name__ == "__main__":
    main()
