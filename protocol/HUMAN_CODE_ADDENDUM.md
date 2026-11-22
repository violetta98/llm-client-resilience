# Addendum: timeout constructs in human-written HTTP client code (D64, post hoc)

Written and hashed on 2026-11-22, before any package was downloaded. Not deposited with a third party.

## Question

Are per-read timeouts without a whole-call deadline also the norm in human-written Python HTTP client code, or is
the construct split of the article specific to LLM-generated code? Static comparison only: the human code is parsed,
never run.

## Sample

- Population: the 500 most downloaded PyPI packages in the 30-day list of `top-pypi-packages`
  (https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json), fetched once; the file, its date
  and SHA-256 are kept.
- For each package, the source distribution (`.tar.gz`) of the latest release listed by the PyPI JSON API; if there is
  none, the pure-Python wheel (`py3-none-any`). Name, version, URL and SHA-256 of each file are recorded. Archives are
  read with Python's `tarfile`/`zipfile` without extracting to disk.
- Excluded: the HTTP client libraries themselves (requests, httpx, httpcore, aiohttp, urllib3); files under a directory
  named tests, test, testing, docs, doc, examples, example, benchmarks, vendor, `_vendor`, vendored.

## Unit and classification

- Unit (primary): a function or method (innermost `def`/`async def`) in a module that imports requests, httpx or
  aiohttp, containing an HTTP call: `requests.<m>(`, `httpx.<m>(`, or `<recv>.<m>(` where the last name of `<recv>`
  contains `session`, `client` or `http` (case-insensitive), with `<m>` in get, post, put, patch, delete, head,
  options, request, send, stream.
- Each unit is classified with the frozen classifier of the article (`classify/features.py`, `classify_python`) on the
  module's import statements plus the function source, and grouped as in Fig. 3 (`analysis/variants_analysis.py`,
  `construct_group`): whole-call deadline, per-read or until-headers only, no timeout.
- Also recorded: whether the HTTP call passes a `timeout=` argument at all (a library function may leave the timeout
  to its caller).
- Sensitivity: the same classification on the whole module (a deadline may be set by a caller in the same file).

## Comparison and reporting

- Shares of units in each group, with 95 % bootstrap intervals over packages (2,000 resamples, seed 20261106), and the
  share of packages with at least one unit in each group.
- Compared with the LLM-generated Python solutions (runnable, both conditions; and the baseline only): 124 whole-call,
  620 per-read or until-headers only, 5 no timeout (both conditions), from `data/features.csv`.
- Descriptive only; no hypothesis test. Reported whatever the result.

## Limitations stated in advance

Library and SDK code differs from the single-purpose functions of the benchmark; callers outside the module may set a
deadline; the regex for receivers misses some clients and may include non-HTTP objects; static labels are not
behavior (the article's classifier agrees with the author's labels on whole-call deadlines in 94 % of 100 solutions).
