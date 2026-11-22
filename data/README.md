# Summary data

Derived from the raw run directories in the Zenodo data record (main README, *Getting the data*), so that a number in
the paper can be checked without downloading 0.95 GB. The raw files are described in `SCHEMA.md` of the data record.

| File | Content | Written by |
|---|---|---|
| `programs.csv` | one row per generation (3,072) and its category | `analysis/collect.py` |
| `runs.csv` | one row per run (29,180 at 90 s, 180 repetitions at 330 s), every measure | `analysis/collect.py` |
| `rep-runs.csv` | the same for the repeatability run | `analysis/collect.py` |
| `primary.csv` | the three primary outcomes per program (input of `analysis/models.R`) | `analysis/primary.py` |
| `features.csv` | classifier labels: library, timeout constructs, retry mechanism | `classify/features.py` |
| `coverage.json` | runs expected, present, usable; harness failures | `analysis/collect.py` |
| `tables/` | the paper's tables as CSV (earlier numbering, see the main README) | `analysis/paper_tables.py` |
| `baselines/` | default calls of the 15 libraries (Online Resource 1, Table A4) | `analysis/e4_baselines.py` |
| other folders | one per experiment or analysis, mapped to the paper in the main README | see the main README |
| `manual_check.csv`, `manual_checks/` | the author's blind labels and the verdicts of the author's checks | by hand |

Before opening a file:

- Only `usable` runs count: the harness check passed and the call produced a result.
- Empty means "not applicable", not zero (for example `unsafe_write_retry` outside S8).
- Shares in `tables/` are fractions with 95% bootstrap intervals over the 16 tasks (2,000 resamples, seed 20261106):
  `_lo`/`_hi` interval, `_n` denominator, `_events` numerator.

## Keys

`(cond, model, task, lang, sample)` identifies a program, for example `C2/claude-opus-5.5/W1/python/2`; adding
`scenario` (S0–S9) and `limit_s` (90, or 330 for a repetition) identifies a run. Model ids and dated snapshots are in
`gen/config/main.json`.

## Generation categories (`programs.csv`)

| Category | Count | Meaning |
|---|---|---|
| `ok` | 2,531 | prepared and imported; runs in every scenario of its task |
| `import_error` | 35 | the import fails in every run (D33) |
| `compile_error` | 398 | transpilation, `javac` or `go build` failed (Python: syntax error) |
| `missing_dependency` | 104 | imports a module not installed in the pinned image |
| `no_code` | 4 | no extractable code |

## Main columns of `runs.csv`

| Column | Meaning |
|---|---|
| `status` | driver result: `returned`, `raised`, `mixed` (S7), `no_return`, `import_error`, ... |
| `no_return`, `no_return_90` | some invocation did not return within `limit_s` (`_90`: S1–S4 only) |
| `time_limit_s`, `overrun` | the task's stated limit (B: 30 s, H: 1–3 s); returned more than 0.25 s after it, or not at all |
| `outcome`, `outcome_allowed`, `silent_failure` | result class; whether Table 3 allows it; a disallowed result reported as success |
| `rapid_retries` | three or more attempts of one logical call, each gap under 100 ms |
| `excessive_retries` | more than 10 attempts of one logical call in the 30 s outage (S7) or within 30 s (S9) |
| `retry_after_violation` | S6: an attempt earlier than Retry-After allows (0.1 s or 1 s tolerance) |
| `sync_retries` | S7: more than 0.8 of the k-th attempts of the ten invocations fall in one 50 ms window |
| `unsafe_write_retry` | S8: a second payment (W1), SMS (W2) or delivery (B4) |
| `late_requests` | requests within 5 s after the function returned |
| `harness_ok`, `usable` | clocks, capture and result intact; usable as defined above |

Connection-level scenarios (S1, S2, S9) count attempts as new source ports in the packet capture (D15). `SCHEMA.md`
in the data record lists every column with its unit.
