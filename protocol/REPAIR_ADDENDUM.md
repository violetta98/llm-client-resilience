# Protocol addendum: experiment B, repair with fault-injection feedback

Status: **frozen 2026-11-14** (hashes in `protocol/REPAIR_FREEZE.json`), before any repair prompt was sent; the author may
deposit it. It does not change protocol v1 or any result of the main run.

## Question
RQ6 (Repair). When a model receives the failing fault-injection tests of its own solution, how often does its revised
solution pass them, and what does the revision break?

This addresses the practical use of the benchmark: a developer runs the tests of the paper's Table 16 against
generated code and pastes the failures back into the model.

## Population
Every runnable C0 solution of the main run (`usable` runs, 90 s limit) that failed at least one of the following, in
any scenario:
- no return within 90 s;
- time-limit overrun (B and H tasks);
- excessive or rapid retries in S7 or S9;
- Retry-After violation in S6a or S6b;
- unsafe write retry in S8;
- silent failure.

`gen/repair_prompts.py` selects these: 661 solutions with 1,121 failed tests, from 68 to 113 per model.
Synchronized retries and late requests are not used for selection; they are the least repeatable measure and an
ambiguous one. C2 solutions are not repaired.

## Treatment
One request per selected solution, to the model that wrote it, with the same provider, parameters, output limit and
mode (batch or synchronous) as in the main run (`gen/config/repair.json`). The prompt is the C0 task prompt without
its last line, followed by four parts:
1. the solution as extracted;
2. a numbered list of the failed tests, each with three parts: the stub's behaviour (Table III wording), what was
   observed, and what the test expects (Tables IV and V wording);
3. "Fix the function so that these tests pass and it still works when the API behaves normally.";
4. the original last line.

The report says nothing about how to fix the code. Code is extracted by the fixed rule of the main run. One attempt,
with no further rounds.

## Measurement
Each revised solution is prepared and run in all scenarios exactly as in the main run (same images, harness, mock,
thresholds, 330 s repetitions). The repetition sample is not repeated.

## Outcomes
- **Primary:** *fixed*, meaning the revised solution is runnable and none of the tests that the original failed fails
  again. A non-runnable revision counts as not fixed.
- **Secondary, descriptive:**
  - fixed per failure type (no return, overrun, excessive/rapid, Retry-After, unsafe write, silent failure), per
    model and per language;
  - regressions: a test the original passed and the revision fails, in any scenario, including the S0 outcome;
  - new harmful retries;
  - change in the anti-patterns of the paper (AP1–AP9), including whether a whole-call deadline appears (classifier
    as corrected in D34).

## Reference without feedback
For each selected solution, the share of the other C0 samples of the same model, task and language that pass the
same tests is computed from the main run, at no cost. It estimates what re-generation without feedback would
achieve. The share of C2 samples that pass them is a second reference, for requirements without feedback.

## Analysis
- Proportions with 95 % intervals from a bootstrap over tasks (2,000 resamples, seed 20261106), per model and
  overall.
- The single preregistered test: fixed (repair) vs passing (sibling reference), paired by solution. It uses a
  logistic mixed model `y ~ arm + (1 | task) + (1 | model) + (1 | solution)` in glmmTMB, with the bootstrap over
  tasks as fallback in the order of protocol v1.
- Everything else is descriptive.

## Cost and budget
Expected generation cost is about 21 USD. That is 661 requests: mean output tokens of the selected solutions in the
main run × list or batch price, plus prompts of about 7,600 characters. Kimi K3 accounts for about 15 USD of it. The
cap for this run is the remainder of the study cap, `BUDGET_USD=90.16` (180 − 89.84 spent in the main run), enforced
per request by `gen/generate.py` and `gen/batch.py`. Runs: about 7,800, roughly one day on three slots.

## Deviations
Any departure is recorded in `DEVIATIONS.md` with its date, as for protocol v1.

## Amendment 1 (2026-11-15): arm R1, review without feedback (DEVIATIONS D39)
Added after review, before any R1 request was sent (R0 requests had been sent). For each of the same 661 solutions, the same model receives the C0 task prompt without its last line, the solution, and: "Review this function for resilience to a slow, failing, or rate-limiting API, and improve it where needed. It must still work when the API behaves normally." followed by the original last line — no test report. Revisions are run exactly as in R0. R1 is the reference for the effect of the feedback: *fixed* (R0) vs *fixed* (R1), paired by solution, with the model `y ~ arm + (1 | task) + (1 | model) + (1 | solution)`; the sibling reference stays descriptive. Revisions of both arms are additionally run in the S4 variants (0.5 s, 5 s, headers only; D38) to check whether fixes generalize beyond the fault parameters of the report. Hashes: `protocol/REPAIR_FREEZE.json`, key `arm_R1`.
