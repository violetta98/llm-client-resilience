"""Agreement between the automatic classification and the author's blind manual check (E9).

  python3 classify/agreement.py --run main   -> analysis/out/classify_agreement.csv (+ printed summary)

Per feature: percent agreement and Cohen's kappa over the 100 programs; rows the author left empty are skipped.
library is compared as a set (';'-joined); retry_mechanism likewise. whole_call (added 2026-11-17, D41) compares the
author's judgement "a deadline bounds the whole call, body included" with the classifier's whole-call constructs
(the set WHOLE of analysis/s4_mechanism.py); the column is optional and skipped when absent.
"""
from __future__ import annotations

import argparse
import sys
import collections
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
FEATS = ("library", "timeout_explicit", "timeout_total", "retry_mechanism", "whole_call")
sys.path.insert(0, str(REPO / "analysis"))
from s4_mechanism import WHOLE  # noqa: E402


def norm(v):
    return ";".join(sorted(x.strip() for x in str(v).split(";") if x.strip()))


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in ca) / n / n
    return None if pe == 1 else (po - pe) / (1 - pe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    d = REPO / "data" / a.run / "classify"
    auto = {tuple(r[k] for k in KEYS): r for r in csv.DictReader(open(d / "features.csv"))}
    man = list(csv.DictReader(open(d / "manual_check.csv")))
    out = []
    def auto_val(r, f):
        if f == "whole_call":
            cons = {c.strip() for c in r.get("timeout_constructs", "").split(";") if c.strip()}
            return "1" if cons & WHOLE else "0"
        return norm(r[f])

    for f in FEATS:
        col = f"author_{f}"
        pairs = [(auto_val(auto[tuple(m[k] for k in KEYS)], f), norm(m[col])) for m in man if (m.get(col) or "").strip()]
        agree = sum(x == y for x, y in pairs)
        k = kappa(pairs)
        out.append({"feature": f, "n": len(pairs), "agree": agree, "percent": round(100 * agree / len(pairs), 1) if pairs else "",
                    "kappa": round(k, 3) if k is not None else ""})
    od = REPO / "analysis" / "out"
    od.mkdir(parents=True, exist_ok=True)
    with open(od / "classify_agreement.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(out[0]))
        w.writeheader()
        w.writerows(out)
    for r in out:
        print(r)


if __name__ == "__main__":
    main()
