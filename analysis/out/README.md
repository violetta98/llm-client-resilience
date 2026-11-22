# analysis/out: what each file is and where it comes from

RQ numbers are the paper's; file names keep the protocol's (protocol RQ1 and RQ2 = paper RQ1, protocol RQ3-RQ5 = paper RQ2-RQ4).

`make analyze` regenerates `main/` from `data/main/` and `data/main-rep/` (inputs are named in each script). Shares
have 95% bootstrap intervals over tasks; only `usable` runs count (D33); nothing is imputed.

| File | Paper | Script |
|---|---|---|
| `table_ix.csv`, `table_ix.md`, `baselines_raw.json` | Online Resource 1, Table A4 (library defaults) | `e4_baselines.py` |
| `main/programs.csv` | counts in Sects. 5 and 6 | `collect.py` |
| `main/runs.jsonl`, `main/runs.csv` | all measures, one row per (program, scenario, limit) | `collect.py` |
| `main/coverage.json` | runs expected / present / harness not ok | `collect.py` |
| `main/primary.csv` | RQ3 input: three primary outcomes per solution | `primary.py` |
| `main/primary_fits.csv` | RQ3: fit used per outcome (fallback step, warnings) | `models.R` |
| `main/primary_contrasts.csv` | RQ3: Family A (C2 vs C0 per LLM) and B (flagship vs others) | `models.R` |
| `main/primary_cells.csv` | RQ3: raw proportions per LLM x condition, separation flags | `models.R` |
| `main/rq1_no_return_90.csv` | Table 7: no return in 90 s by phase S1–S4, model, condition | `descriptive.py` |
| `main/rq1_km.csv`, `main/fig_rq1_km.png/.pdf` | Online Resource 1, Fig. E1: Kaplan–Meier time to return, S1–S4 per language | `descriptive.py` |
| `main/rq1_rerun330_class.csv`, `main/rq1_rerun330_class_runs.csv` | Table 7: OS-bounded / library-bounded / not bounded | `descriptive.py` |
| `main/rq1_s4_mechanism.csv` | RQ1, exploratory (D32): S4 no return by kind of timeout construct | `s4_mechanism.py` |
| `main/rq1_overrun_by_scenario.csv` | Table 7: time-limit overruns, B and H tasks, per scenario | `descriptive.py` |
| `main/rq2_outcomes_s5_s6.csv` | RQ1: recovered / degraded / failed / silent in S5, S6 | `descriptive.py` |
| `main/rq2_measures.csv` | RQ1: rapid retries, Retry-After violations, excessive, late, synchronized, unsafe write | `descriptive.py` |
| `main/rq2_s7_load.csv` | RQ1: requests to the faulted dependency in S7 | `descriptive.py` |
| `main/rq3_features.csv` | RQ2: library choice, explicit timeouts, retry mechanism | `descriptive.py` |
| `main/rq3_vs_baseline.csv`, `main/rq3_vs_baseline_runs.csv` | RQ2: match / better / worse than library default | `vs_baseline.py` |
| `main/rq3_harmful_source.csv` | RQ2: harmful retries from library defaults vs generated code | `vs_baseline.py` |
| `main/rq4_by_condition.csv` | RQ3: every measure by condition and model | `descriptive.py` |
| `main/rq5_linters.csv` | RQ4: recall and false alarms of Bandit B113, Ruff S113, noctx | `descriptive.py` |
| `main/also_categories.csv` | ok / import_error / compile_error / missing_dependency / no_code | `descriptive.py` |
| `main/also_distinct.csv` | distinct solutions per task | `descriptive.py` |
| `main/also_tokens_cost.csv` | tokens, cost, latency, providers per model | `descriptive.py` |
| `main/also_repeatability.csv`, `main/also_repeatability_pairs.csv` | repeatability: agreement and Cohen's kappa per measure | `repeatability.py` |
| `main/paper/table*.csv` | Tables 7–10 and Fig. 3 (file names keep earlier numbers; see `data/README.md`) | `paper_tables.py` |
| `main-rep/*` | measures of the repeatability run | `collect.py --run main-rep` |
| `classify_agreement.csv` | Sect. 4.6: automatic vs manual labels (percent, kappa) | `classify/agreement.py` |

Operational rules fixed during the analysis are in `DEVIATIONS.md` D29–D32.
