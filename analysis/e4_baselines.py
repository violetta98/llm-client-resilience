"""E4: behavior of each HTTP client library's default call under every
scenario (draft Table IX; RQ3). Input: an E4 run directory (baselines run by
tests/integration/e3_run.py --index baselines/index.json --long-rerun).
Output: analysis/out/table_ix.csv, table_ix.md (one cell per library x
program x scenario) and baselines_raw.json.
Usage: python3 analysis/e4_baselines.py data/dev/e4/baselines data/dev/e4/s4lead-baselines
"""
import csv
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402

SC = ["S0", "S1", "S2", "S3", "S4", "S5a", "S5b", "S6a", "S6b", "S7", "S8", "S9"]
ORDER = ["urllib.request", "requests", "urllib3", "httpx", "aiohttp", "fetch", "axios", "got", "ky",
         "java.net.http", "okhttp", "apache-httpclient5", "net-http", "resty", "go-retryablehttp"]


def cell(r, r330):
    """Compact description of one run: outcome, time, attempts."""
    c = (r.get("durations_s") or [None])[0]
    sc = r["scenario"]
    att = r["n_conn_attempts_faulted_dep"] if sc in ("S1", "S2", "S9") else r["n_requests_faulted_dep"]
    if r.get("no_return"):
        if r330 is None:
            t = "no return in 90 s"
        elif r330.get("no_return"):
            t = "no return in 330 s"
        else:
            d = (r330.get("durations_s") or [None])[0]
            t = f"{r330.get('outcome')} after {d:.1f} s (330 s run)"
            att = r330["n_conn_attempts_faulted_dep"] if sc in ("S1", "S2", "S9") else r330["n_requests_faulted_dep"]
    elif sc == "S7":
        outs = r.get("outcomes") or []
        durs = [d for d in r.get("durations_s") or [] if d is not None]
        t = f"{'/'.join(sorted(set(outs)))} after {min(durs):.1f}–{max(durs):.1f} s" if durs else str(outs)
        att = r.get("load_requests_total")
    else:
        t = f"{r.get('outcome')} after {c:.2f} s" if c is not None else str(r.get("outcome"))
    extra = []
    if r.get("retry_after_violation"):
        extra.append("Retry-After violated")
    if r.get("unsafe_write_retry"):
        extra.append("DUPLICATE write")
    if r.get("rapid_retries"):
        extra.append("rapid")
    if r.get("excessive_retries"):
        extra.append("excessive")
    if r.get("sync_retries"):
        extra.append("synchronized retries")
    if sc == "S7" and r.get("sync_shares"):
        extra.append(f"max share {max(r['sync_shares'].values()):.1f} (intervals {max((r.get('sync_gap_shares') or {0: 0}).values()):.1f})")
    if r.get("late_requests"):
        extra.append(f"{r['late_requests']} late")
    unit = "requests during outage" if sc == "S7" else ("connection attempts" if sc in ("S1", "S2", "S9") else "requests")
    return f"{t}; {att} {unit}" + (f"; {', '.join(extra)}" if extra else "")


def main(*bases):
    """Later run directories replace earlier ones for the scenarios they contain
    (e.g. data/dev/e4/s4lead-baselines replaces S4 after D19)."""
    rows = {}
    for base in map(Path, bases):
        new = {}
        for d in sorted(base.glob("runs/*/*/BASELINE-*/*")):
            lang, task, variant, sc = d.parts[-4:]
            exp = yaml.safe_load((REPO / "tasks" / task / "expected.yaml").read_text())
            r = M.compute(M.load_run(d), exp)
            r["source_dir"] = str(d)
            lib, prog = variant[len("BASELINE-"):].rsplit("-", 1)
            new[(lib, prog, sc)] = r
        replaced = {k[2].split("-")[0] for k in new}
        rows = {k: v for k, v in rows.items() if k[2].split("-")[0] not in replaced}
        rows.update(new)
    out = REPO / "analysis" / "out"
    out.mkdir(parents=True, exist_ok=True)
    table = []
    for lib in ORDER:
        for prog in ("get", "post"):
            line = {"library": lib, "program": prog.upper()}
            for sc in SC:
                r = rows.get((lib, prog, sc))
                if r is None:
                    line[sc] = "—"
                    continue
                line[sc] = cell(r, rows.get((lib, prog, sc + "-330")))
            table.append(line)
    with open(out / "table_ix.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["library", "program"] + SC)
        w.writeheader()
        w.writerows(table)
    md = ["| Library | Call | " + " | ".join(SC) + " |", "|---|---|" + "---|" * len(SC)]
    for line in table:
        md.append(f"| {line['library']} | {line['program']} | " + " | ".join(line[s] for s in SC) + " |")
    (out / "table_ix.md").write_text("\n".join(md) + "\n")
    (out / "baselines_raw.json").write_text(json.dumps({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in rows.items()}, indent=1, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main(*sys.argv[1:])
