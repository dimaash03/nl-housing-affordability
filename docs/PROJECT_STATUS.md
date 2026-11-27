# Project status

**Last updated:** 2026-11-27
**Current stage:** 3. Marts (star schema) — complete (PR #11 merged); review follow-ups in PR #12; next 4. analysis notebook + 5. Power BI

Stages: 1. Scoping / data sourcing → 2. Ingestion & staging → 3. Marts (star schema) → 4. Analysis (notebooks) → 5. Power BI dashboard → 6. Write-up (README insights, limitations).

## Done
- Stage 1 (PR #1): sources verified, data dictionary, decisions D-001…D-017.
- Stage 2 (PRs #2–#7): ingestion, DuckDB raw/staging, SQL data tests, geo boundary code, herindeling mapping
  (445 historical codes → 342), stage-2 QA review and fixes. Decisions D-018…D-025 approved 2026-11-26.
- Stage 3 (PR #8): `marts.fct_affordability`, 342 × 15 = 5 130 rows.
- 2026-11-26: full pipeline reproduced from a fresh clone on the owner's Mac (`make ingest load transform check test`).
- 2026-11-26: `cpi_2025_index` and `real_median_disposable_income_eur_2025` added to the fact (D-027);
  `is_harmonised` definition fixed at 311 rows (D-026) — PR #9, merged.
- 2026-11-26: `dim_municipality` (342), `dim_province` (12), `dim_year` (15); data tests for star-schema integrity
  and the D-016 2 % income validation (+0.47 … +0.99 % in 2011–2025). PR #10 merged, D-028 approved.
- 2026-11-26: `fct_group_affordability` (270 rows: NL, provinces, G4 / Rest of NL, three-way split) with
  `assert_group_aggregates.sql`; `make export` (marts → `data/processed/marts/*.parquet`). D-029 proposed.
  G4 PTI 2011 9.41 → 2024 12.12; Rest of NL 7.16 → 8.72 (2025 preliminary: 12.01 / 8.97). PR #11 merged 2026-11-27.
- 2026-11-27 (PR #12, owner review follow-ups): README synced to the real state (stages, data model, group methods,
  run order with expected results, limitations); config `project:` is the single source of truth via
  `reference.project_settings` (D-031); `dim_year.is_latest_data_year` from loaded data (D-030);
  `is_income_approximated` in `fct_group_affordability`; new checks `assert_dimensions_match_source`,
  `assert_region_groups`, `assert_project_settings` (21 checks); `make check` before `make transform` names the
  missing step; Python ≥ 3.11 / DuckDB ≥ 2.0.1 (D-032); `loopback` pytest marker; GitHub Actions CI (3.11 lower
  bounds + 3.13 locked, geo extras, no skips) and a manual full-pipeline job; `make build`, `make reproduce`.
  Verified from a fresh download: 12 models, 21/21 checks, 174 tests (Python 3.13 locked and 3.11 lower bounds).

## Next steps (towards the dashboard)
1. Owner reviews PR #12 (decide D-030, D-031, D-032; D-029 status), merges, then
   `git pull && make setup && make build && make test`.
2. Stage 4 analysis notebook `notebooks/01_affordability_findings.ipynb`: 3–5 checked findings, each with a
   sensitivity check (owner-occupier income, 2024 instead of 2025*, real vs nominal, quality-adjusted index for
   G4/provinces, rank stability without low-reliability municipalities) and the PTI limitations.
3. Stage 5 Power BI: import the Parquet files, star schema, DAX measures, 4 pages (KPI overview, map,
   G4 vs regions, municipality detail).
4. Public one-page case-study site (GitHub Pages) at the end.

## Open items
- Owner: `make setup-geo && make geo` on the Mac (PDOK), then commit `data/reference/municipalities_2026.*`.
- Owner: `make lock` on the Mac (P-6: the lock was generated on Linux / Python 3.13).
- PDOK licence (D-014) — confirm before committing the boundary file.
- Historical mortgage-rate series (D-013, stretch) — owner downloads from DNB manually.
- End of project: "defend your decisions" walkthrough of D-001…D-032 with the owner.

## Key facts (do not re-derive)
- Years covered: 2011–2025 (set in `config/cbs_tables.yaml` `project:`); 2025 income preliminary (`Perioden.Status = 'Voorlopig'`).
- Municipality list version: gemeentelijke indeling 2026 (342 municipalities, `86247NED`).
- G4 codes: GM0363 Amsterdam, GM0599 Rotterdam, GM0518 's-Gravenhage, GM0344 Utrecht.
- Randstad provinces (secondary split): PV26 Utrecht, PV27 Noord-Holland, PV28 Zuid-Holland.
- Group PTI is never the mean of municipal PTIs (D-016).
