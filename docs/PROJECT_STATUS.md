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

## Stage 2 — merged / in review
- Merged: #2 pipeline & staging, #3 geo boundaries.
- Stage-2 QA review (`docs/reviews/2026-11-22_stage2_qa_review.md`, PR #6). Every finding is fixed except P-6:
  - #5: ingest retries pages whose response body breaks off (P-1, major).
  - #7: geo G-1…G-6 (lint, string `jaarcode`, holes matched one by one, files checked after rounding, `make geo`,
    `Content-Crs` per page), pipeline P-2…P-5 (whole-percent owner share from 2021, stale tables dropped,
    period-status test), D-011 reworded, decision IDs D-018…D-025 (proposed).
  - #4 harmonisation: H-1…H-7 fixed on the branch (committed mapping loaded by `make load`, `make harmonise`,
    `assert_mapping_covers_staging.sql`, doc SQL equals the Python reference for 5 130/5 130 municipality-years).
- Integration (scratch merge #4 + #5 + #7, 2026-11-22 download): 151 tests, lint clean, `make check` 15/15.
- Merge order: #5 → #7 → #4 → #6.

## Stage-2 QA review (2026-11-22)
- Report: `docs/reviews/2026-11-22_stage2_qa_review.md`. #2 and #3 are merged; #4 is open and ready on correctness.
- Fixed: P-1, ingest retry of broken response bodies (PR #5).
- Open before stage 3: `make lint` is red on `main` (geo, G-1); #4 needs `make format` (H-1), a decision on the
  numbering of the proposed decisions (H-2), loading the committed mapping in the standard pipeline (H-3) and a
  mapping ↔ staging data test (H-5).

## Next steps (after stage 2 is merged)
1. Stage 3: `int_*` harmonised models, `fct_affordability`, `dim_municipality`, `dim_province`, `dim_year`,
   group aggregates (D-016) with the validation test (< 2 % vs official NL median). Owner drafts `fct_affordability` first.
2. Parquet export for Power BI (`make export`).

## Open items
- Owner: approve D-018…D-025 (logged as proposed).
- Owner: `make setup-geo && make geo` on the Mac (PDOK), then commit `data/reference/municipalities_2026.*`.
- Owner: `make lock` on the Mac (P-6: the lock was generated on Linux / Python 3.13).
- PDOK licence (D-014) — confirm before committing the boundary file.
- Historical mortgage-rate series (D-013, stretch) — owner downloads from DNB manually.
- Power BI refresh: Parquet export (planned) vs DuckDB ODBC driver.

## Key facts (do not re-derive)
- Years covered: 2011–2025; 2025 income preliminary (`Perioden.Status = 'Voorlopig'`).
- Municipality list version: gemeentelijke indeling 2026 (342 municipalities, `86247NED`).
- G4 codes: GM0363 Amsterdam, GM0599 Rotterdam, GM0518 's-Gravenhage, GM0344 Utrecht.
- Randstad provinces (secondary split): PV26 Utrecht, PV27 Noord-Holland, PV28 Zuid-Holland.
