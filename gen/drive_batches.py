"""Submits batch chunks that fit the gateway balance and collects them, until every batch model is done (E7).

  BUDGET_USD=180 python3 gen/drive_batches.py --config gen/config/main.json [--models a,b] [--margin 8]

OpenRouter reserves the worst case of a batch (max_tokens per request) at submit and returns the rest on
completion, so a chunk is sized to (available balance - margin) / worst case per request. One open batch per
model. The study's own cap (BUDGET_USD, spent + outstanding worst case) is still checked by gen/batch.py.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch as B  # noqa: E402
import generate as G  # noqa: E402
import providers as PV  # noqa: E402


def available(key):
    st, d = B.http("GET", "https://openrouter.ai/api/v1/credits", key)
    if st != 200:
        return None
    return d["data"]["total_credits"] - d["data"]["total_usage"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--models", default="")
    ap.add_argument("--margin", type=float, default=8.0, help="USD left free for the sync workers")
    ap.add_argument("--max-chunk", type=int, default=400)
    ap.add_argument("--sync-reserve", type=float, default=40.0, help="USD of the study cap kept free for sync models")
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    base = B.REPO / "data" / cfg["run"]
    models = [m for m in cfg["models"] if m.get("mode") == "batch" and (not a.models or m["id"] in a.models.split(","))]
    while True:
        try:
            B.poll(cfg, wait=False)
        except Exception as e:  # noqa: BLE001  (network hiccup: try again next round)
            print(f"poll: {e!r}", flush=True)
        recs = [json.loads(p.read_text()) for p in (base / "batches").glob("*.json")]
        open_models = {r["model_id"] for r in recs if not r.get("collected")}
        todo = 0
        for m in models:
            pend = list(B.pending(cfg, m, cfg["conditions"], base))
            todo += len(pend) + (m["id"] in open_models)
            if not pend or m["id"] in open_models:
                continue
            key = PV._key(m)
            avail = available(key)
            if avail is None:
                continue
            per = max(G.worst_case_cost(m, G.prompt_for(t, l, c, cfg, m["id"], smp)) for c, t, l, smp, _ in pend[:20])
            bud = G.Budget(base / "costs.jsonl")  # study cap: leave room for the sync workers (they wait while batches hold it)
            room = (bud.cap or 0) - bud.spent - bud.held - a.sync_reserve
            n = min(len(pend), a.max_chunk, int((avail - a.margin) / per), int(room / per))
            if n < 1:
                print(f"{G.now()} {m['id']}: {len(pend)} pending, available {avail:.2f} USD is too low for one request", flush=True)
                continue
            try:
                r = B.submit(cfg, m, cfg["conditions"], n, False)
                print(f"{G.now()} {m['id']}: submitted {r}", flush=True)
                open_models.add(m["id"])
            except SystemExit as e:
                print(f"{G.now()} {m['id']}: {e}", flush=True)
        if todo == 0:
            print("all batch models done", flush=True)
            return
        time.sleep(120)


if __name__ == "__main__":
    main()
