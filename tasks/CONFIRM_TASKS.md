# Confirmatory tasks R6, W5, B5, H4

Four new benchmark tasks for a preregistered confirmatory replication, one per group of the
original 16. They were added **after** the protocol-v1 freeze (`protocol/FREEZE.json`) and are
outside that protocol. Nothing that existed before was changed: every frozen file, every file
of the 16 tasks, the pilot tasks, the existing references, mutants and index files and all run
configurations are byte-identical (checked by SHA-256 over the whole tree, `data/` and `dist/`
excluded, before and after the files below were added).

## The four tasks

| ID | Group | Function | Request | Time limit | Allowed outcomes (S1–S9) |
|---|---|---|---|---|---|
| R6 | read | `get_stock_levels(base_url, product_id) -> object` | `GET /v1/products/{product_id}/stock` | none (10 s in C2) | correct or error |
| W5 | write | `create_ticket(base_url, customer_id, subject, message) -> object` | `POST /v1/tickets`, Idempotency-Key **accepted** | none (10 s in C2) | correct or error; S8 defined |
| B5 | background | `fetch_shipment_updates(base_url, carrier_id, since) -> objects` | `GET /v1/carriers/{carrier_id}/shipment-updates?since=…` | 30 s (nightly batch job) | correct or error; S7: error |
| H4 | handler | `get_notification_preferences(preferences_url, user_id) -> object` | `GET /v1/users/{user_id}/notification-preferences` | 2 s (web request handler) | correct or degraded; S7: degraded |

- **R6** fetches a product's stock levels in 24 warehouses (JSON body about 1.5 KB). Unlike R1 (small
  profile object), R2 (query string), R3 (binary download), R4 (pagination) and R5 (default value),
  the result is a nested JSON object that has to arrive completely.
- **W5** opens a support ticket. The API excerpt carries the same idempotency sentence as W1
  (`IDEM_YES`, "…create at most one ticket"), so S8 (the request is processed, then the connection is
  reset) is defined: a retry is safe only with the same Idempotency-Key. The mock stores keys like W1
  (same key and body → stored 201 replayed; same key, other body → 422; no key → a new ticket every time).
- **B5** fetches one response of shipment status updates of a carrier after `since` (25 updates,
  about 2.3 KB) for a nightly sync. Following `next_since` ends with an empty page, so a program
  that paginates terminates.
- **H4** returns the notification preferences or, if they cannot be obtained in time, the documented
  default `{"email": true, "sms": false, "push": false}`. The mock returns the opposite value in every
  field, so the default is distinguishable from a real value (as in R5, H2, P3).

## Why they are comparable to the original groups

- **Same templates.** The prompts are rendered by the functions of `tasks/generate.py`
  (`prompt`, `task_body`, `api_block`, `signature`, `subst`) with the constants of `tasks/catalog.py`:
  the same openers, the same two operational lines (429/Retry-After, 503; "Typical latency 150 ms,
  p99 800 ms"), the identical "Available: …" line per language, the same C1 and C2 texts and final
  line. The neutrality checks of `generate.py` (no "timeout", "retry", "backoff", … in C0/C1) pass:
  `tasks/confirm_checks.json`. Prompts were rendered for C0, C1 and C2 in all four languages
  (48 files), although the confirmatory run uses C0 and C2 only.
- **Same group conventions.** Read and write tasks state no time limit (the C2 limit of 10 s applies);
  the background task states the 30 s limit with the same sentence as B1–B4 ("it must return or raise
  within 30 s"); the handler task states 2 s and a documented degraded result like H1/P3. `expected.yaml`
  is produced by `generate.py`'s `expected()`, so the allowed outcomes follow the same rules:
  read/write/background → correct or error; handler → correct or degraded, never an error; background
  S7 → error (a 30 s outage cannot be outlasted within 30 s); handler S7 → degraded; write tasks also
  run S8. W5's `unsafe_effect: ticket_created` lets `analysis/measures.py` (generic branch, as for the
  pilot task P2) flag a second ticket in S8.
- **Same fault model.** Every task has a single dependency A on port 9001, every request to the
  documented endpoint is the faulted request (as R1, R5, H2), and the logical-call key contains the
  argument that differs between the ten S7 invocations, so attempts, synchronized retries and late
  requests are attributed exactly as for the original tasks (`measures.invocation_of`, unit-tested).
  The JSON bodies of R6 and B5 are below the S4 trickle length (4096 bytes), so S4 delivers the
  complete, valid body one byte every 2 s (padded with leading whitespace, D19).
- **Same call plan.** `signature.json` has `warmup_args` (id …-000, warm-up port), `single_args`
  (id …-042) and ten `s7_args` (ids …-100 … -109); `runner/run_generated.py` and
  `tests/integration/e3_run.py` build the plan from it exactly as for the other tasks (mode `single`
  with one call, `concurrent` with the ten S7 calls). Argument and return types are ones the drivers
  already handle (str; object, objects).
- **Same references and mutants.** The reference bodies use the shared preludes unchanged
  (`references/src/<lang>/prelude.*`, 9.5 s budget without a limit, 28 s for the 30 s job, limit − 0.2 s
  = 1.8 s for the handler). Mutants are the five of `references/build.py`; UNSAFE_POST_RETRY applies to
  W5 only (a new Idempotency-Key per attempt, as for W1). In TypeScript and Java the benchmark has
  mutants for one task per group (R1, W1, B2, H3); the confirmatory set has exactly one task per group,
  so all four get mutants in all four languages (21 programs per language). None of the mutants is
  inapplicable by construction (H4's 1.8 s budget leaves room for a Retry-After violation and a second
  attempt, as in H1).

## What is not covered by the frozen harness, and how it is handled

1. **Result checks.** `analysis/checkers.py` (frozen) raises `KeyError` for an unknown task, which
   `e3_run.py` and `run_generated.py` would record as a harness error. The checks of the four tasks are in
   `analysis/checkers_confirm.py`; its `install()` wraps `checkers.check` (other tasks are passed to the
   original unchanged). Two new entry points install it and then call the unchanged `main()`:
   `tests/integration/e3_confirm.py` (= `e3_run.py`) and `runner/run_confirm.py` (= `run_generated.py`).
   The later analysis (`make analyze`) would need the same `install()` before it recomputes measures.
2. **No scenario filter in `run_generated.py`.** It runs every scenario listed in each task's
   `expected.yaml` (11, or 12 for W5) and then the 330 s repetitions (S1–S4 runs without return).
   Restricting the confirmatory run to S0 S3 S4 S7 S9 needs a minimal change, **not made**: an argument
   `ap.add_argument("--scenarios", default="")` and, in the job loop,
   `for sc in (a.variants.split(",") if a.variants_of else [s for s in exp[t]["scenarios"] if not a.scenarios or s in a.scenarios.split(",")]):`
   (the same filter `e3_run.py` already has). Add `--no-rerun` to skip the 330 s repetitions of S3/S4.
3. **Mock image.** The handlers are in a new file `mock/tasks_confirm.go` (registered by `init()`, like
   `tasks_pilot.go`); the image `lcr-mock:dev` must be rebuilt before the new tasks can run. Rebuild it
   only when no experiment is running: the orchestrator always uses the tag `lcr-mock:dev` and records the
   image ID per run, and the behavior of the existing tasks is unchanged. The other images are unchanged.
4. **Generated header.** The reference files say "Generated by references/build.py" because
   `build_confirm.py` uses `build.py`'s `render()`; they are produced by `references/build_confirm.py`.

## Files added

Task definitions and generation
- `tasks/confirm_catalog.py` — catalog entries of R6, W5, B5, H4 (same schema as `tasks/catalog.py`; imports `IDEM_YES` from it), plus the expected-data helpers used by the checks
- `tasks/generate_confirm.py` — renders the four tasks with the functions of `tasks/generate.py` (unchanged); `python3 tasks/generate_confirm.py`
- `tasks/confirm_checks.json` — uniformity / neutrality checks of the 48 new prompts
- `tasks/CONFIRM_TASKS.md` — this file
- `tasks/{R6,W5,B5,H4}/spec.md`, `api_doc.md`, `expected.yaml`, `signature.json`
- `tasks/{R6,W5,B5,H4}/prompts/{python,typescript,java,go}/{C0,C1,C2}.txt` (48 files)

Mock
- `mock/tasks_confirm.go` — Classify + Handle, effects (`ticket_created`, `ticket_replayed`), logical-call keys (`stock:<id>`, `ticket:<customer_id>`, `updates:<carrier>|<since>`, `prefs:<user>`)
- `mock/tasks_confirm_test.go` — `TestConfirmTasks` (normal behavior, keys, faulted flags, S3/S5a/S6a, idempotency, warm-up ids, S4 body length)

References and mutants
- `references/src/{python,typescript,java,go}/confirm_tasks.py` — task bodies (loaded into the namespace of `tasks.py`, like `pilot_tasks.py`)
- `references/build_confirm.py` — assembles them with `references/build.py` (unchanged); `python3 references/build_confirm.py`
- `references/{R6,W5,B5,H4}/{python,typescript,java,go}/solution.*` (16 files)
- `mutants/{R6,B5,H4}/<lang>/{NO_TIMEOUT,TIGHT_LOOP,IGNORE_RETRY_AFTER,FIXED_BACKOFF}/solution.*` and `mutants/W5/<lang>/{… ,UNSAFE_POST_RETRY}/solution.*` (68 files)
- `references/index-confirm-{python,typescript,java,go}.json` — 21 programs each

Measures, entry points, tests, configuration
- `analysis/checkers_confirm.py` — result checks of the four tasks; `install()`
- `tests/integration/e3_confirm.py` — `e3_run.py` with the checks installed
- `runner/run_confirm.py` — `run_generated.py` with the checks installed
- `tests/unit/test_confirm_tasks.py` — generated files, checks (same literal values as the Go test), S7 attribution, S8 unsafe-retry and S7 outcome measures
- `gen/config/confirm.json` — run `confirm`: the eight models of `gen/config/main.json` with identical provider and request parameters, C0 and C2, tasks R6 W5 B5 H4, four languages, 3 samples (768 requests); `budget_usd: 25.0` documents the cap, which the scripts enforce through `BUDGET_USD=25`

## Commands (not run here)

```
# 1. mock image (only lcr-mock:dev changes); when no experiment is running
docker build -f runner/images/mock.Dockerfile -t lcr-mock:dev --build-arg VERSION=$(git describe --always --dirty 2>/dev/null || echo dev) .
make test-mock && python3 -m unittest tests/unit/test_confirm_tasks.py

# 2. references and mutants, one language per call (e3_run's --index is one file for all --langs)
make clean-slots
for L in python typescript java go; do
  python3 tests/integration/e3_confirm.py --langs $L --index references/index-confirm-$L.json --slots 3 --out dev/e3/confirm-$L
done
# verdicts: data/dev/e3/confirm-<lang>/summary.json (all_references_pass, all_mutants_flagged)

# 3. generation (paid; author only) and runs
export OPENROUTER_API_KEY=...; export BUDGET_USD=25
python3 gen/drive_batches.py --config gen/config/confirm.json --sync-reserve 5   # default reserve 40 USD exceeds the 25 USD cap
python3 gen/generate.py --config gen/config/confirm.json
make clean-slots
nohup caffeinate -i python3 runner/run_confirm.py --run confirm --slots 3 > data/confirm/run.log 2>&1 &
```
Step 3 runs every scenario of each task (see item 2 above for the S0 S3 S4 S7 S9 restriction).
