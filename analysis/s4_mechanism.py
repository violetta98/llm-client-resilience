"""Exploratory (post hoc, DEVIATIONS D32): which timeout constructs bound S4 (body trickled at 1 byte / 2 s).

  python3 analysis/s4_mechanism.py [--run main]

Reads  analysis/out/<run>/runs.jsonl, data/<run>/classify/features.csv
Writes analysis/out/<run>/rq1_s4_mechanism.csv  lang, group, solutions, no_return_90, share
Groups by the strongest whole-call deadline the classifier found in the solution:
  whole-call deadline  Python asyncio.timeout / asyncio.timeout_at / asyncio.wait_for / aiohttp.ClientTimeout /
                       concurrent.futures result(timeout), wait/as_completed(timeout) (D34);
                       Java Future.get(timeout) / orTimeout / OkHttp callTimeout; TypeScript AbortSignal.timeout /
                       AbortController+setTimeout / setTimeout(timeout); Go context.WithTimeout / http.Client.Timeout
  per-read or until-headers only  every other timeout construct (requests/httpx/urllib3 timeout=, Java
                       HttpRequest.Builder.timeout, connectTimeout, setReadTimeout, ky/got timeout option, ...)
  no timeout           no construct found
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
WHOLE = {"asyncio.timeout", "asyncio.timeout_at", "asyncio.wait_for", "aiohttp.ClientTimeout(total)",
         "Future.get(timeout)", "Future.result(timeout)", "orTimeout", "callTimeout",
         "AbortSignal.timeout", "AbortController+setTimeout", "Promise.race+setTimeout",
         "context.WithTimeout", "http.Client.Timeout",
         # D44: also bound the whole call
         "async_timeout.timeout", "resty SetTimeout", "ky timeout", "got timeout.request"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    feats = {tuple(r[k] for k in KEYS): r for r in csv.DictReader(open(REPO / "data" / a.run / "classify" / "features.csv"))}
    agg = defaultdict(lambda: [0, 0])
    for line in open(REPO / "analysis" / "out" / a.run / "runs.jsonl"):
        r = json.loads(line)
        if r["limit_s"] != 90 or r["scenario"] != "S4" or not r.get("usable"):
            continue
        f = feats[tuple(str(r[k]) for k in KEYS)]
        t = {x for x in f["timeout_constructs"].split(";") if x}
        g = "whole-call deadline" if t & WHOLE else "per-read or until-headers only" if t else "no timeout"
        for key in ((r["lang"], g), ("all", g)):
            agg[key][0] += 1
            agg[key][1] += int(bool(r.get("no_return_90")))
    out = REPO / "analysis" / "out" / a.run / "rq1_s4_mechanism.csv"
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["lang", "group", "solutions", "no_return_90", "share"])
        for (lang, g), (n, k) in sorted(agg.items()):
            w.writerow([lang, g, n, k, round(k / n, 4)])
            print(f"{lang:10s} {g:32s} {n:5d} {k:5d} {100 * k / n:5.1f} %")


if __name__ == "__main__":
    main()
