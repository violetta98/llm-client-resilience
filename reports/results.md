# Results

Findings of the study, by research question of the paper (protocol RQ numbers in parentheses). Shares are of runnable
solutions in the baseline condition (C0; 1,271 of the 2,531) unless stated. Intervals and per-model figures are in the paper and in
`data/tables/`. Registered: specified in the protocol; exploratory: an analysis of registered data that the protocol
did not specify; post hoc: data or analyses added after the main results were known (`DEVIATIONS.md`, D32–D63).

## RQ1: Failures (protocol RQ1 and RQ2; registered, descriptive)

- Few solutions hang while waiting for a connection or the response headers: 1.4 % in S1, 0.9 % in S2, 3.8 % in S3.
- When the body arrives one byte every 2 s (S4), 34.8 % do not return within 90 s (48.8 % in tasks without a stated
  limit). Of the 1,120 solutions to tasks with a time limit (B and H), 19.6 % overrun it in at least one scenario (both
  conditions), most of them in S4.
- Most solutions write their own retries (83.3 % in C0, 97.9 % in C2). During the 30 s outage (S7), 10.2 % make more
  than ten attempts per call (6.8 % without the polling task B2); most of them back off, but with short delays.
- Duplicate writes after a reset are rare: a second SMS in W2 only; no payment or webhook delivery is duplicated.
- Only 1.7 % send an HTTP request after the function returned; the registered late-request measure (10.2 %) also
  counts library connection attempts (D49).
- Data: `data/tables/table07_stalls.csv`, `data/tables/table08_retries.csv`, `data/review10/summary.json`.

## RQ2: Causes (protocol RQ3; constructs exploratory, runtime version post hoc)

- The models choose the standard or most popular client of each language. Its defaults bound neither a slow body
  (only ky and aiohttp end it) nor, in most cases, a stalled response, and the solutions improve on them; 3 of the
  1,957 retry flags in solutions with their own retries match the library default (`data/results/rq3_counterfactual.csv`).
- S4 hangs follow the timeout construct: 2.2 % with a whole-call deadline, 73.7 % with only per-read or until-headers
  timeouts (exploratory); without Java 2.6 % and 67.1 %; leaving out any one model or task keeps the difference at
  61.6–69.0 pp without Java (post hoc, D61).
- The libraries' documentation examples (19, in `docs_examples/`) teach the same construct: in S4, 11 do not return
  within 90 s and 3 more only after 33–65 s; only 4 recover from a 503 burst (post hoc, D61).
- Java: rerun on JDK 26, which applies the request timeout to the body, 160 of the 162 hanging baseline solutions return
  without a code change (258 of 264 over both conditions; post hoc, D52). With these runs, the baseline S4 rate would be
  22.2 % (Online Resource 1, Table A5). The held-out and repair Java solutions behave the same way (D53).
- Data: `data/tables/table09_library_defaults.csv`, `data/tables/table12_s4_mechanism.csv`, `data/main-jdk26/`.

## RQ3: Prevention by stated requirements (protocol RQ4)

- Registered: only one of the 24 preregistered per-model tests is significant (fewer overruns for Claude Haiku 5.5),
  and none with the Java solutions on JDK 26; the tests had little power.
- Exploratory: in tasks without a stated limit, explicit requirements (C2) reduce S4 hangs from 48.8 % to 32.4 %
  (about half that effect with the Java solutions on JDK 26) and make retries more aggressive: excessive retries in S7
  or S9 rise from 11.5 % to 32.1 %, mostly within the time budget the requirements set.
- Post hoc ablation on the held-out tasks (hypotheses frozen in `protocol/ABLATION_ADDENDUM.md`): one line capping the
  attempts at four lowers excessive retries in S7 from 26.1 % to 0.3 %; without the 429/503 and latency lines of the API
  excerpt, 43.3 % of the baseline solutions retry during the outage instead of 90.3 %, and fewer recover from a 503 or
  a 429. S4 hangs with the capped prompt stay below the baseline (37.3 % vs 52.3 %), but with the Java solutions on
  JDK 26 the difference shrinks to −7.6 pp, an interval that includes zero.
- Data: `data/tables/table10_primary.csv`, `data/ablation/`, `data/review11/summary.json`.

## RQ4: Detection by static checks (protocol RQ5)

- Bandit B113 and Ruff S113 flag about 1 % of the failing Python solutions, because nearly all of them pass
  `timeout=`. In Go, noctx catches most of the few failing solutions, with many false alarms.
- Exploratory: flagging solutions without a whole-call deadline finds most hangs, but in Java its value depends on the
  JDK. Revised after the author's manual checks (post hoc, D61), it finds 97.6 % of the failing solutions with 184 false
  alarms (94.2 % and 248 before). Only 157 of the 440 failing Python solutions make a call that B113 inspects.
- Data: `data/tables/table11_linters.csv`.

## RQ5: Repair with failing tests (addendum RQ6, added after the main results)

- With a report of the failed fault tests, 79.3 % of the failing solutions were fixed; after a review request without
  the report, 29.7 % (paired by solution, 653 solutions). Fixed without any new failing test: 73.5 % vs 26.2 %.
- Of the report-guided revisions that pass S4 at the 2 s gap, 95.5 % also pass at 0.5 s, at 5 s and with headers
  only, gaps the report did not name (`data/variants/revisions_g5h.csv`).
- Granite and Qwen fix about a third and often break other tests.
- Data: `data/repair/`.

## Held-out tasks

Four tasks written after the main results (R6, W5, B5, H4), 768 generations, 621 runnable solutions with usable runs,
hypotheses and scripts frozen before the first request (`protocol/CONFIRM_ADDENDUM.md`, not deposited with a third
party). The paper calls the hypotheses HO1–HO4 (H1–H4 in the addendum and in `data/confirm/`, not to be confused with
the handler tasks H1–H4). One-sided tests, Holm over HO1–HO3; differences with a bootstrap over models, which holds the tasks fixed.

| Hypothesis | Comparison | Difference (pp, 95 % CI over models) | p |
|---|---|---|---|
| HO1: S4 hang, no whole-call deadline vs deadline | 75.2 % vs 1.7 % (200/266 vs 6/355) | 73.5 (62.9–79.8) | < 1e-13 (near separation) |
| HO2: S4 hang in R6/W5, requirements vs baseline | 35.4 % vs 52.3 % | −16.9 (−30.2 to −3.8) | < 1e-4 |
| HO3: S7 excessive retries, requirements vs baseline | 26.1 % vs 7.2 % | 18.8 (6.6–30.8) | < 1e-4 |
| HO4: flagged among 114 failing Python solutions | B113 2.6 %, S113 0.9 % (test vs 10 %) | — | 0.003, < 1e-4 |

With the Java S4 runs on JDK 26 (post hoc), HO2 becomes 25.9 % vs 32.3 %, −6.4 (−17.4 to 7.7), an interval that
includes zero. Data: `data/confirm/`, `data/review11/summary.json`.

## Constructs that avoid the anti-patterns (Online Resource 1, Sect. D; post hoc)

Programs in `advice/`, written for this check by the AI assistant (not by an evaluated model), were run against the mock
and against local servers. Results:
`data/advice/`, `data/advice-ra30/`, `advice/gzip_check/result*.txt`, `advice/java_check/result.txt`.
