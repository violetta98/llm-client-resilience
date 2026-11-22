"""Assembles the reference solutions and mutants of the CONFIRMATORY tasks R6, W5, B5, H4
(tasks/CONFIRM_TASKS.md) from references/src/<lang>/ (shared prelude + tasks.py helpers +
confirm_tasks.py bodies), with the functions of references/build.py, which is not changed.

  python3 references/build_confirm.py            # all four languages

references/<ID>/<lang>/solution.<ext>          MUTANT = NONE
mutants/<ID>/<lang>/<MUTANT>/solution.<ext>    one property removed (references/README.md)
references/index-confirm-<lang>.json           program index for tests/integration/e3_confirm.py --index

Mutants: the five of build.py. Every confirmatory task gets them in every language: in
TypeScript and Java the benchmark has mutants for one task per group (R1, W1, B2, H3); the
confirmatory set has exactly one task per group. UNSAFE_POST_RETRY applies to W5 (like W1:
a new Idempotency-Key per attempt, and the POST retried after a failure that may have been
processed); it is not applicable to the GET tasks R6, B5, H4.
The existing references, mutants and index files are not touched.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402  (references/build.py; main() is not called)

REPO = B.REPO
TASKS = ["R6", "W5", "B5", "H4"]
UNSAFE_TASKS = {"W5"}
LANGS = ["python", "typescript", "java", "go"]


def load(lang):
    mod = B.load(lang)
    exec((B.SRC / lang / "confirm_tasks.py").read_text(), mod.__dict__)
    return mod


def applicable(task, mutant):
    return mutant != "UNSAFE_POST_RETRY" or task in UNSAFE_TASKS


def main(langs):
    for lang in langs:
        mod = load(lang)
        index = []
        for t in TASKS:
            out = REPO / "references" / t / lang / f"solution.{B.EXT[lang]}"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(B.render(lang, t, "NONE", mod))
            index.append({"task": t, "lang": lang, "variant": "REFERENCE", "path": str(out.relative_to(REPO))})
            for m in B.MUTANTS:
                if not applicable(t, m):
                    continue
                out = REPO / "mutants" / t / lang / m / f"solution.{B.EXT[lang]}"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(B.render(lang, t, m, mod))
                index.append({"task": t, "lang": lang, "variant": m, "path": str(out.relative_to(REPO))})
        (REPO / "references" / f"index-confirm-{lang}.json").write_text(json.dumps(index, indent=1))
        print(f"{lang}: {len(index)} programs")


if __name__ == "__main__":
    main(sys.argv[1:] or LANGS)
