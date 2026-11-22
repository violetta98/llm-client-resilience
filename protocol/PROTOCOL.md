# Protocol v1 — Timeouts and retries in LLM-generated HTTP client code

Frozen at stage E6 and deposited before any benchmark task is sent to any model. Everything below is
fixed; any later change is a deviation recorded in `DEVIATIONS.md` with its reason.

## 1. Design (D21)
- **Models (Table VI)**, all through the OpenRouter gateway, identifiers and dated snapshots in `gen/config/main.json`:
  Claude Opus 5.5, GPT-6.1 Sol, Gemini 4 Argon (flagships); Claude Haiku 5.5 (small proprietary);
  DeepSeek V4.1 Flash (snapshot 2026-10-17), Kimi K3, Qwen3-Coder-Next (open); Granite 4.2 8B (small open, ≤ 10B).
- **Provider policy:** the model vendor's own endpoint where the gateway has one; otherwise the cheapest unquantized (bf16)
  endpoint; pinned with `allow_fallbacks: false`. Endpoints that may train on prompts are excluded (account privacy
  setting), so that the benchmark tasks do not enter training data; then the cheapest endpoint serving the weights as
  released by the vendor is used (DeepSeek V4.1 Flash: DeepInfra, FP8 = the released precision). Batches for Gemini 4 Argon
  run on Google Vertex (AI Studio has no batch endpoint for it). The provider that served each response is logged.
  Checked before the freeze with one request of pilot task P1 per model (`gen/config/probe.json`, `data/probe/`).
- **Generation parameters:** `max_tokens` 64,000; temperature, top-p and reasoning effort at the provider's defaults;
  `seed` = 1000·sample + 1 where the API accepts one (Anthropic does not). One user message, no system prompt.
  Batch APIs for the four proprietary models; synchronous requests for the others (Kimi K3's batch endpoint caps output at
  16,384 tokens).
- **Tasks:** the 16 tasks in `tasks/` (R1–R5, W1–W4, B1–B4, H1–H3) with `spec.md`, `api_doc.md`, `signature.json`,
  `expected.yaml` (Table IV: allowed outcomes per scenario).
- **Languages:** Python 3.13.18, TypeScript on Node.js 26.12.1, Java (Temurin JDK 25.0.5), Go 1.27.3 (images pinned by digest, libraries by lock files;
  `environment.json` in the bundle).
- **Conditions:** C0 (task only) and C2 (explicit requirements). C1 is not run (D21); its templates are kept in the bundle.
- **Samples:** 3 per (model, task, language, condition) → 8 × 16 × 4 × 3 × 2 = **3,072 programs**.

## 2. Code extraction and preparation
- Extraction (`gen/extract.py`): the last non-empty fenced block whose info string names the target language; otherwise the
  whole response if it contains no fence (Python: must parse; other languages: a compile error then means `no_code`);
  otherwise `no_code`.
- Preparation (`runner/prepare.py`): categories `ok`, `compile_error`, `missing_dependency` (imports a module that is not
  installed in the pinned image; preparation runs without network), `no_code`, `api_error`. Only `ok` programs are run; all categories are reported.

## 3. Execution
- Mock service and scenarios S0–S9 as in `mock/` (Table III); S4 pads the body with leading whitespace (D19).
- Every `ok` program runs in every scenario listed in its task's `expected.yaml`; one fresh container pair per run;
  90 s limit (`protocol/thresholds.json`).
- **330 s repetitions:** every run without return in 90 s in S1–S3; in S4 every Python program importing aiohttp plus a
  deterministic 10 % sample (SHA-256 of `cond/model/task/lang/sample` < 0.1 · 2³²; `runner/run_generated.py`).
- **Repeatability:** a 5 % sample of `ok` programs (same hash rule with threshold 0.05 on the key prefixed `rep:`) is run a
  second time in all its scenarios under a new run ID (`runner/run_generated.py --run main-rep --rep-of main`;
  167 of the 3,072 keys); agreement of outcomes is reported.

## 4. Measures and thresholds
Table V measures as implemented in `analysis/measures.py` and `analysis/checkers.py`, thresholds in
`protocol/thresholds.json` (synchronized-retry threshold 0.8 on the Table V share; D18). Harness validation (references,
mutants, library baselines) in `reports/e3_harness.md` and `analysis/out/table_ix.*`.

## 5. Primary outcomes (fixed in advance)
1. No return within 90 s in S3.
2. Time-limit overrun in background (B) and handler (H) tasks, any scenario (threshold: limit + `overrun_margin_s`).
3. Unsafe write retry in S8 (W1, W2, B4).

Analysis of these and of all secondary measures: `protocol/ANALYSIS_PLAN.md`.

## 6. Spending
`BUDGET_USD` = 180 (hard cap, checked before every request or batch against spent + outstanding worst case). For each model
the first ≈5 % of requests (19) are generated first; if the projected cost of that model exceeds its `high_scenario_usd` in
the config, generation stops and the author is asked.
