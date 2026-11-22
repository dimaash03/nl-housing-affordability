# Project status

**Last updated:** 2026-11-22
**Current stage:** 2. Ingestion & staging

Stages: 1. Scoping / data sourcing → 2. Ingestion & staging → 3. Marts (star schema) → 4. Analysis (notebooks) → 5. Power BI dashboard → 6. Write-up (README insights, limitations).

## Done
- Project skeleton: folder structure, README, CLAUDE.md, Makefile, requirements, `.gitignore`.
- `nl_housing.ingest` (idempotent CBS OData downloader) and `nl_housing.load_duckdb` (`raw` schema), 31 offline tests.
- Stage 1 data research (PR #1): sources verified, data dictionary, decisions log.
- 2026-11-22 review of PR #1 and the scaffold: key values re-checked against the API, all open questions decided
  (D-003 … D-017), findings listed in `docs/reviews/2026-11-22_research_review.md`.

## In progress (stage 2, parallel branches)
1. `feat/pipeline-staging` — retries for CBS requests (C1), SQL runner `nl_housing.transform` (C2), staging models for
   all 7 tables, data tests (C3), lock file + ruff (C4, C5); real `make ingest && make load && make transform` with row counts.
2. `feat/harmonisation` — tested parser of `70739ned/RegioS` descriptions → `data/reference/municipality_mapping_2026.csv`,
   weight sensitivity (D-007).
3. `feat/geo-boundaries` — `nl_housing.geo` script for PDOK boundaries + licence check (D-014). The download itself is
   run by the owner locally (PDOK not reachable from the agent environment).

## Stage 3 started (2026-11-22)
- `feat/fct-affordability` (PR #8) — `marts.fct_affordability` (342 x 15 = 5 130 rows), stacked on the unmerged
  `feat/harmonisation` (PR #4) for `reference.municipality_mapping_2026`. Checks in the PR: grain, PTI nulls
  (3 in 2025), Amsterdam PTI and harmonised price, prices identical to `weight_sensitivity`, D-016 income
  validation (max +0.99 %).

## Next steps (after stage 2 is merged)
1. Stage 3: `int_*` harmonised models, `fct_affordability`, `dim_municipality`, `dim_province`, `dim_year`,
   group aggregates (D-016) with the validation test (< 2 % vs official NL median). Owner drafts `fct_affordability` first.
2. Parquet export for Power BI (`make export`).

## Open items
- PDOK licence (D-014) — confirm before committing the boundary file.
- Historical mortgage-rate series (D-013, stretch) — owner downloads from DNB manually.
- Power BI refresh: Parquet export (planned) vs DuckDB ODBC driver.

## Key facts (do not re-derive)
- Years covered: 2011–2025; 2025 income preliminary (`Perioden.Status = 'Voorlopig'`).
- Municipality list version: gemeentelijke indeling 2026 (342 municipalities, `86247NED`).
- G4 codes: GM0363 Amsterdam, GM0599 Rotterdam, GM0518 's-Gravenhage, GM0344 Utrecht.
- Randstad provinces (secondary split): PV26 Utrecht, PV27 Noord-Holland, PV28 Zuid-Holland.
