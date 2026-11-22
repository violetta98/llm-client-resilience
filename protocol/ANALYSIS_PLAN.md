# Analysis plan (protocol v1)

Unit of analysis: one generated program (solution). Repeated invocations within a run (the ten S7 calls) form one
observation per solution. Programs that are not `ok` are reported by category and excluded from behavioural measures.

## Primary outcomes — inference
For each primary outcome y (PROTOCOL.md §5), a logistic mixed model fitted with **glmmTMB** (R, version pinned in the
analysis environment):

    y ~ llm * condition + language + (1 | task) + (1 | task:language) + (1 | llm:task)

- Unsafe write retry (only W1, W2, B4): `task` enters as a fixed effect and its random terms are removed:
  `y ~ llm * condition + language + task`. In B4 the receiver deduplicates by event id, so this outcome is
  near-structurally zero there (it occurs only if a model changes the event id); B4 is kept and reported separately as well.
- Time-limit overrun: B- and H-tasks only (7 tasks); one observation per (solution, scenario) pooled to "overrun in any
  scenario" per solution.
- **Convergence fallback, fixed order:** if a fit fails (non-convergence or non-positive-definite Hessian), drop
  (1) `(1 | llm:task)`, then (2) `(1 | task:language)`, then (3) `(1 | task)` → plain logistic regression with
  task as a fixed effect if estimable; last resort: a bootstrap over solutions within tasks (2,000 resamples, seed 20261106)
  of the contrasts below. The fit actually used is reported.
- Quasi-complete separation (a cell with 0 % or 100 %): reported as such; the corresponding contrast is tested by the
  bootstrap fallback rather than by Wald.
- **Contrasts** (likelihood-ratio tests where the nested model exists, else Wald), each family Holm-corrected at α = 0.05:
  - Family A — C2 vs C0 within each LLM: 8 contrasts.
  - Family B — flagship (Opus 5.5, GPT-6.1 Sol, Gemini 4 Argon) vs the other five LLMs within each condition: 2 contrasts.
- Effect sizes: odds ratios with 95 % profile (or Wald) intervals; also raw proportions per cell.

## Descriptive analyses (secondary, no hypothesis tests)
- **RQ1:** Kaplan–Meier curves of time to return per scenario S1–S4 and language, censored at 90 s or 330 s for repeated
  runs; no return in 90 s by scenario and model with 95 % intervals from a bootstrap over tasks (2,000 resamples,
  seed 20261106); classification of non-returning runs by the 330 s repetition (OS-bounded / library-bounded / not bounded);
  time-limit overruns for B- and H-tasks per scenario.
- **RQ2:** outcomes in S5 and S6 (recovered / degraded / failed / silent); rapid retries, Retry-After violations, excessive
  retries, late requests, synchronized retries (S7), unsafe write retries; load on the faulted dependency in S7.
- **RQ3:** client library choice per model and language (imports, AST); baselines (Table IX); whether solutions match,
  improve or worsen the library defaults; harmful retries from library defaults vs from generated code.
- **RQ4:** primary outcomes by condition as above; all other measures by condition, descriptively; requirements still
  missed under C2, including C2 overruns.
- **RQ5:** Bandit B113 and Ruff S113 (Python), noctx in golangci-lint (Go), versions pinned, rules enabled explicitly.
  Share of solutions with no return in 90 s or a time-limit overrun that each linter flags; false alarms (flagged but
  returning within limits).
- **Also:** `no_code`, `missing_dependency`, compile errors; distinct solutions; repeatability (5 % sample); tokens, cost and
  latency per model; providers that served each model.

## Classification (E9)
Library, explicit timeouts and retry mechanism by AST/import rules; a manual check of 100 randomly drawn solutions
(seed 20261106) by the author, with agreement reported.

## What is not done
No outcome-driven changes of prompts, thresholds or measures after the freeze; no exclusion of models, tasks or programs
beyond the categories above; every deviation goes to `DEVIATIONS.md`.
