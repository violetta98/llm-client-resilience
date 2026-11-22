# Protocol addendum: confirmatory replication on new tasks

Status: **frozen 2026-11-17** (hashes in `protocol/CONFIRM_FREEZE.json`), before any request of run `confirm` was sent.
It does not change protocol v1, the repair addendum, or any result of the earlier runs.

## Why
In the main study the strongest findings are descriptive or exploratory: the S4 mechanism (a timeout that bounds each
read does not stop a trickled body), the effect of a stated time limit, and more aggressive retries under the
resilience requirements. The preregistered per-model tests had little power. This run tests these findings as
hypotheses, fixed before the data exist, on tasks that did not exist when the findings were made.

## Design
- **Tasks:** four new tasks, one per group, written after the main results and before this run: R6 (read, no time
  limit), W5 (write, no time limit), B5 (background, 30 s), H4 (handler, 2 s). Definitions in `tasks/CONFIRM_TASKS.md`.
- **Models, parameters, prompts, extraction:** as in the main run (`gen/config/confirm.json`), conditions C0 and C2,
  3 samples per cell: 4 tasks × 4 languages × 2 conditions × 8 models × 3 = 768 generations.
- **Scenarios:** S0, S3, S4, S7, S9 (others are not needed for the hypotheses); harness, mock, thresholds, 90 s limit
  and 330 s repetition rules as in protocol v1.
- **Classifier:** `classify/features.py` and the whole-call construct set `WHOLE` of `analysis/s4_mechanism.py`, both
  frozen by hash in `CONFIRM_FREEZE.json` (the versions after D34 and D38). No rule is changed after this run starts.

## Hypotheses (directions fixed by the main study)
Unit: runnable solution. All tests one-sided at α = 0.05, Holm-corrected over H1–H3.

- **H1 (mechanism).** In S4, solutions with no whole-call deadline hang (no return within 90 s) more often than
  solutions with one. Both conditions, all tasks.
- **H2 (stated time limit).** In R6 and W5, which state no time limit, fewer solutions hang in S4 under C2 (which adds
  a 10 s limit) than under C0.
- **H3 (retries).** In S7, more solutions make more than 10 attempts per logical call during the outage under C2 than
  under C0. All tasks.
- **H4 (linters, separate).** Of the failing Python solutions (no return within 90 s in S3 or S4, or a time-limit
  overrun), Bandit B113 and Ruff S113 each flag fewer than 10 %: exact binomial test against 0.10, run only if at
  least 20 failing Python solutions exist; otherwise reported descriptively.

## Analysis
Scripts, frozen with this addendum: `analysis/collect_confirm.py` (measures), `classify/features.py --run confirm`
(classifier), `classify/lint.py --run confirm` (H4), `analysis/confirm_analysis.py` (data, bootstrap, H4) and
`analysis/confirm_model.R` (H1–H3). The run uses `runner/run_confirm.py --run confirm --scenarios S0,S3,S4,S7,S9`.
- H1–H3: logistic mixed model `y ~ x + language + (1 | model) + (1 | task)` in glmmTMB, x = no whole-call deadline
  (H1, with condition as an extra fixed effect) or condition (H2, H3). One-sided p from the Wald z of x. Fallback
  in this order if a fit fails: drop (1 | task), then (1 | model); last resort a bootstrap over models of the
  difference in proportions (2,000 resamples, seed 20261106), one-sided.
- Effect sizes: odds ratio with 95 % interval, and the difference in proportions with a bootstrap interval over
  models.
- Descriptive: S4 hang rate in C0, excessive retries in S7 in C0 and C2, per language; comparison with the main run.
- Runs failing the harness check are repeated, as in protocol v1. Everything else is descriptive.

## Harness validation of the new tasks
References and mutants of R6, W5, B5 and H4 were run in all scenarios before this addendum was frozen
(`data/dev/e3/confirm-<lang>`). Known exceptions, none of which concerns a measure used in H1–H4: the Python
references, which bound a call with an abandoned thread, can send a request after the call returned in S7 (late
requests); the synchronized-retry measure misses fixed-backoff mutants, as in the main study.

## Cost and budget
Expected generation cost about 22.5 USD (5.62 USD per task over all models in the main run; Kimi K3 about 70 %).
Cap for this run: `BUDGET_USD=25`, enforced per request. Study ceiling raised by the author from 180 to 205 USD
(2026-11-17). Runs: about 3,100 at three slots, roughly 12–16 h.

## Deviations
Recorded in `DEVIATIONS.md` (D43 onwards), as for protocol v1.
