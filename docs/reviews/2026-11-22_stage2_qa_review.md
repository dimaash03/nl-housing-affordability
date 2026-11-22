# Stage-2 QA review (2026-11-22)

Independent QA review of the three stage-2 branches, run as a scheduled agent. Every figure below comes from a
command run during this review, on CBS data downloaded on 2026-11-22 through the pipeline on `main`.

| PR | Branch | Head reviewed | State during review | Verdict |
|---|---|---|---|---|
| #2 | `feat/pipeline-staging` | `51ffb4a` (merged as `0868c37`) | merged 11:34 UTC, before the review | changes requested: 1 major (fixed in #5), 3 minor, 2 nit |
| #3 | `feat/geo-boundaries` | `318fb6c` (merged as `6630fd7`) | last commit < 15 min old at the start; merged 11:44 UTC during the review | changes requested: 5 minor, 1 nit, no blocker/major |
| #4 | `feat/harmonisation` | `ab8ab58` | open; last commit < 15 min old at the start, possibly unfinished | changes requested: 6 minor (1 needs an owner decision), 1 nit; ready to merge on correctness |

Severity scale: `blocker` = wrong results or crash; `major` = a stated guarantee does not hold or the pipeline fails
in a realistic case; `minor` = robustness, docs or maintainability issue without wrong numbers; `nit` = cosmetic.

Review comments: #2 (issuecomment-7078721674, follow-up 7078742493), #3 (7078725649 / 7078742673),
#4 (7078732060 / 7078742811). Fix PR: #5.

## 1. Method

- One `git worktree` and one venv per branch (Python 3.13.18). Ran `pytest`, `ruff check`, `ruff format --check`.
- `main` (= #2): real `make ingest && make load && make transform && make check`. Then I compared the PR's claims
  with SQL queries on the resulting DuckDB file and with `DataProperties` (units, decimals) and `Perioden.Status`.
- #4: ran `python -m nl_housing.harmonise` and `python -m nl_housing.weight_sensitivity` on the same raw data and
  compared the output with the committed CSV and the PR body.
- #3: offline only, because PDOK cannot be reached from here. Ran the tests with and without `requirements-geo.txt`,
  plus small experiments (the tolerance unit of `toposimplify`, feature order, a string `jaarcode`).
- Integration: a scratch branch merging `main` + #3 + #4 (no conflicts). On it I ran the full test suite and lint,
  `make load transform`, `harmonise --load-duckdb`, `make check`, and a SQL implementation of the D-007 price and
  household harmonisation, compared against the Python reference.

## 2. What was verified (reproduced)

**Pipeline (#2):**
- `pytest` 59 passed; ruff clean on the branch.
- `make check`: 13/13 pass, also after a second `make transform` run (idempotent).
- Raw row counts: 23 095 / 325 500 / 25 120 / 88 914 / 342 / 1 531 / 3 318.
- Staging row counts: 5 884 / 13 020 / 6 882 / 16 / 342 / 651 / 1 531.
- GM codes with a price per year: 418, 415, 408, 403, 394, 390, 388, 380, 355, 355, 352, 345, 342, 342, 342 (2011–2025).
- 2018 WOZ gaps: GM0417, GM0743, GM0847, GM1702, GM1721. In 2024, 19 municipalities have < 5 000 households.
- Units: households in `86380NED` are `x 1 000`, incomes `1 000 euro`, WOZ `1 000 euro`, counts in `70072ned` are `aantal`.
- Period status: only `86380NED` 2025 is `Voorlopig`. All years of 83625NED, 70072ned, 85792NED and 86141NED are `Definitief`.

**Harmonisation (#4):**
- `pytest` 71 passed.
- 1 131 terminating events (1 069 abolitions, 62 code-changing renames).
- 445 price codes → 342 codes of 2026; 298 municipalities from one code, 44 from several.
- 456 rows: 342 unchanged / 95 merge / 6 split / 2 rename.
- 117 abolitions since 2011 (129 receiver rows); 69 boundary corrections (2 642 inhabitants); 0 end-date mismatches.
- The regenerated CSV is byte-identical to the committed `data/reference/municipality_mapping_2026.csv`.
- Weight sensitivity: 310 of 5 130 harmonised municipality-years. Max / median / p95 difference: dwellings 3.57 / 0.23 / 1.07 %,
  households 4.89 / 0.24 / 1.30 %. Amsterdam 2019–2022: 481 422 · 507 388 · 564 658 · 617 736.
- Harmonised municipality-years per year: 44 (2011), 43, 41, 38, 32, 30, 29, 23 (2018), 11, 11, 6 (2021), 2 (2022), none from 2023.
- The 445 GM codes in 70072ned 2011–2025 are exactly the 445 price codes. The only priced code-year without key figures is GM1940 2015.

**Geo (#3):**
- 53 passed + 1 module skipped without the extras; 63 passed with shapely 2.2.0 / pyproj 3.8.0 / topojson 2.2.
- With `prequantize=True`, `toposimplify` works in metres. A 100 km edge with a 30 m wiggle keeps 46 / 5 vertices at
  10 / 50 m, against 45 / 5 for `shapely.simplify`.
- Feature order and properties survive simplification. Synthetic grid: overlap +3.6e-7 m², 0 new holes.

**Integration (scratch merge of all three):**
- 131 tests pass. No merge conflicts in the Makefile or requirements, because #3 and #4 do not change them.
- The D-007 price pattern in SQL (`staging.stg_cbs__house_prices` ⋈ `stg_cbs__regional_key_figures` ⋈
  `reference.municipality_mapping_2026`) equals `weight_sensitivity.harmonised_prices()` for 5 129 of 5 130
  municipality-years. The exception is GM1940 2015: SQL gives 203 762, the reference 205 512 (see H-4).
- Harmonised households (sum of `households_count * weight`) equal `NL01` in every year 2011–2025 (difference < 1e-9).
- Column contract for stage 3: mapping `old_code` ↔ staging `region_code`; `new_code_2026` ↔
  `stg_cbs__municipalities_2026.municipality_code` ↔ geo `statcode`. All are trimmed `GMxxxx` strings, so no renaming is needed.

## 3. Findings

### PR #2 — pipeline & staging

| ID | Severity | Where | Problem / failure scenario | Fix | Status |
|---|---|---|---|---|---|
| P-1 | major | `src/nl_housing/ingest.py:130-142` | urllib3 `Retry` ends at the status line. A 200 response whose body breaks off (`ChunkedEncodingError`) or is truncated JSON failed the whole table. Reproduced: 1 request, no retry. | Retry the page for body errors (3×, 2/4/8 s). Regression tests. | **fixed** `cb0f126`, PR #5 |
| P-2 | minor | `sql/staging/stg_cbs__regional_key_figures.sql:10-11` | Comment says the share is rounded to 0.1 %. From 2021 `Koopwoningen_64` holds only whole percentages: 0 non-integer GM values per year in 2021–2025, 318–376 per year in 2011–2020. | Correct the comment; document the limitation. | open |
| P-3 | minor | `src/nl_housing/transform.py:140-164` | A model removed from or renamed in `models.yaml` leaves its old table, which marts or Power BI can still read. | Drop unmanaged tables in the managed schemas inside the transaction. | open |
| P-4 | minor | `src/nl_housing/load_duckdb.py:85-132` | Same for `raw.cbs_*` tables of tables that were removed from `data/raw/`. | Drop the orphans or recreate the `raw` schema. | open |
| P-5 | nit | price / key-figure staging | Only income carries the period status. Nothing would flag a future `Voorlopig` price year. | Add a status assertion. | open |
| P-6 | nit | `requirements.lock` | Needs Python ≥ 3.12; `requires-python` says ≥ 3.10 (known). | `make lock` on the owner's Mac. | open |

### PR #3 — geo boundaries

| ID | Severity | Where | Problem / failure scenario | Fix | Status |
|---|---|---|---|---|---|
| G-1 | minor | `geo.py:328, 332, 458`; `tests/geo_fixtures.py:66`; `tests/test_geo.py:3`; `tests/test_geo_simplify.py:14` | Branch predates the ruff config. `make lint` on `main` now fails (7 findings, 4 files to reformat). | `ruff check --fix`, `strict=True`, `ruff format`. | open |
| G-2 | minor | `geo.py:336-340` | A string `jaarcode` fails validation with "jaarcode other than 2026: 2026" (reproduced with the fixture), which would stop the owner's only real run. | Compare as strings. | open |
| G-3 | minor | `geo.py:415-421` | The gap check uses the *net* hole count. Closing *k* existing holes (enclaves, lakes) while opening *k* gaps passes. | Count new holes that don't intersect an original hole. | open |
| G-4 | minor | `geo.py:546-565` | Checks run before rounding and quantization. Invalid geometries after rounding only log a warning, and the TopoJSON is not checked. | Fail on invalid output; validate the decoded TopoJSON. | open |
| G-5 | minor | `Makefile`, lock | No `make geo` target; geo extras not pinned. | Add the target and pin the extras. | open |
| G-6 | nit | `geo.py:272-288` | `Content-Crs` is checked on the last page only. Not hit with 342 features at `limit=1000`. | Check it per page. | open |

### PR #4 — harmonisation

| ID | Severity | Where | Problem / failure scenario | Fix | Status |
|---|---|---|---|---|---|
| H-1 | minor | `harmonise.py:303`; `weight_sensitivity.py:94, 96, 98, 124, 171, 176`; `tests/test_harmonise.py:41, 127, 289` | Adds 10 ruff findings and 4 unformatted files to `main`. | Merge `main` into the branch, then `make format`. | open |
| H-2 | minor | PR body | Proposed D-018…D-021 collide with the D-018…D-021 of #2 (different decisions). | Owner assigns the IDs (e.g. D-022…D-025). | **needs owner decision** |
| H-3 | minor | `harmonise.py:617-623`; Makefile | `--load-duckdb` regenerates the CSV from raw before loading. There is no way to load the committed file alone, and no `make harmonise`. Stage-3 marts depend on it. | Load-only path (or load `data/reference/*.csv` in `make load`) + `make harmonise`. | open |
| H-4 | minor | `docs/harmonisation.md:36-48` | The SQL pattern uses names that don't exist in staging. With the real names it silently gives GM1940 2015 = 203 762 instead of 205 512. | Real names; show and test the GM1940-2015 case. | open |
| H-5 | minor | `sql/tests/` | No data test ties the committed mapping to the staging data, so a stale CSV would drop codes silently. | `assert_mapping_covers_staging.sql`. | open |
| H-6 | minor | `docs/harmonisation.md` §7 | Whole-percent owner share since 2021 (see P-2) affects the 6 + 2 harmonised municipality-years of 2021–2022, including Amsterdam + Weesp. | Document it. | open |
| H-7 | nit | `weight_sensitivity.py:58-80` | `PSEUDO_CODES` not filtered (no effect today). | Filter them. | open |

## 4. Fixes made

- `cb0f126` (branch `fix/pipeline-staging-qa`, PR #5): page-level retry of `ChunkedEncodingError`,
  `ContentDecodingError` and `JSONDecodeError` in `ingest.fetch_all`. Three new tests in `tests/test_retries.py`
  fail before the fix (`ChunkedEncodingError` / `JSONDecodeError`) and pass after it. Full suite: 84 passed, 1 skipped.
  Real `--table 85792NED` download OK. #2 was already merged, so the fix is a new PR instead of a commit on its branch.

No commits were pushed to `feat/harmonisation` or `feat/geo-boundaries`: they have no blocker or major findings.

## 5. Needs owner decision

- **H-2**: numbering of the proposed decisions from #2 (models.yaml order, dropping empty rows, SQL data tests,
  `is_preliminary`) and #4 (mid-year rename, pseudo-municipalities, boundary corrections not modelled, split weights).
- From the earlier review, still open: reword D-011 (the 2018 gaps are in WOZ). Verified again here.

## 6. Recommended order

1. Merge **#5** (P-1 fix; small, tests only touch `ingest`).
2. Small follow-up PR for **G-1 + G-2**, so that `make lint` is green on `main` and the owner's PDOK run cannot fail on the `jaarcode` type.
3. On #4: merge `main` into the branch and run `make format` (H-1). Decide H-2, then merge **#4**.
4. Before stage 3: H-3 (load the committed mapping in the standard pipeline), H-5 (mapping ↔ staging data test), H-4 (doc SQL).
   Then the owner drafts `fct_affordability`.
