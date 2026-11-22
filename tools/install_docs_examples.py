"""D61: copy the documentation examples of docs_examples/<task>/<name>.<ext> into the generation layout of run `docs`
(data/docs/generations/DOC/<name>/<task>/<lang>/1/solution.<ext> + meta.json), so that runner/run_generated.py prepares
and runs them like generated solutions. Each is a timeout or retry example from a library's official documentation,
placed unchanged in the same minimal R1 function (docs_examples/README.md).
"""
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LANG = {"py": "python", "ts": "typescript", "java": "java", "go": "go"}
n = 0
for f in sorted((REPO / "docs_examples").glob("*/*.*")):
    task, name, ext = f.parent.name, f.stem, f.suffix[1:]
    if not (REPO / "tasks" / task).is_dir():  # e.g. a non-task folder
        continue
    d = REPO / "data" / "docs" / "generations" / "DOC" / name / task / LANG[ext] / "1"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(f, d / f"solution.{ext}")
    (d / "meta.json").write_text(json.dumps({"status": "ok", "model_id": name, "note": "documentation example in the minimal R1 function (D61)",
                                             "extraction": {"status": "fenced", "n_blocks": 1, "n_target_blocks": 1}}, indent=1))
    n += 1
print(n, "programs installed")
