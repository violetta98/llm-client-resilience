# Addendum: prompt ablation on the held-out tasks (D51)

Written and frozen (SHA-256 in `protocol/ABLATION_FREEZE.json`) before the first generation request of this run.
Added after the main, held-out and revision results were known, at the request of the round-8 reviewers, with the
author's approval of the cost (cap 30 USD; `BUDGET_USD=28` per process).

## Question

1. Do the operational lines of the baseline prompt ("429: rate limited, see Retry-After. 503: temporarily
   unavailable." and "Typical latency 150 ms, p99 800 ms.") make models write retries and timeouts they would
   otherwise omit?
2. Does an explicit attempt limit in the requirements prompt remove the rise in excessive retries while keeping the
   fewer trickled-body hangs?

## Design

- Tasks R6, W5, B5, H4 (the held-out tasks; `tasks/CONFIRM_TASKS.md`), 4 languages, the same 8 models, providers
  and parameters as `gen/config/confirm.json`, 3 samples per cell: 2 x 8 x 4 x 4 x 3 = 768 requests
  (`gen/config/ablation.json`; Claude models through the batch interface in chunks, the others in sync mode; prompts in `gen/prompts_ablation/`).
- **C0b** (bare baseline): the C0 prompt of `tasks/<task>/prompts/<lang>/C0.txt` without the two operational lines
  above. Nothing else changes; the idempotency sentence of W5 stays, because it describes the API.
- **C2c** (requirements with a cap): the C2 prompt plus one requirement line:
  "- Each request is attempted at most 4 times in total, including the first attempt."
- Comparisons use the existing C0 and C2 solutions of the same tasks from the held-out run (`data/confirm`).
- Scenarios: S0, S3, S4, S5a, S6a, S7, S9 for C0b and C2c (`runner/run_confirm.py --scenarios ...`). S5a and S6a
  are also run for the existing C0 and C2 solutions (run ID `confirm-s56`, same programs, no regeneration).
- Measures: `analysis/measures.py` unchanged. Unit: runnable solution with usable 90 s runs in S0, S3, S4, S7 and
  S9 (as in the held-out analysis).

## Hypotheses (one-sided, alpha = 0.05, Holm over P1-P3)

- **P1** In S7, fewer solutions make more than ten attempts per call under C2c than under C2.
- **P2** In R6 and W5 (no stated limit), fewer solutions hang in S4 under C2c than under C0.
- **P3** In S7, fewer solutions retry at all (more than one attempt for some logical call during the outage)
  under C0b than under C0.

Test: `y ~ c + lang + (1|model) + (1|task)` with glmmTMB, one-sided Wald test of `c`; fallback to fewer random terms
in the order of `analysis/confirm_model.R`; then Fisher's exact test if no model fits.

## Descriptive (no test)

- C0b vs C0: no return in 90 s in S3 and S4; recovery in S5a and S6a; Retry-After violations in S6a; excessive
  retries in S7 and S9; share of runnable generations.
- C2c vs C2: S4 hangs in R6/W5; overruns of the 10 s requirement and of stated limits (computed from the call
  durations, because `measures.py` marks the 10 s requirement only for condition `C2`); S7 attempts per call
  (median, 90th percentile); S9 excessive and rapid retries; recovery in S5a and S6a.

## What would count against the paper

P3 not supported and C0b close to C0 would mean the cues do not drive the retry behavior. P1 not supported would
mean an attempt limit in the prompt does not fix the rise; P2 not supported would mean the cap removes the benefit.
All results are reported whatever their direction.
