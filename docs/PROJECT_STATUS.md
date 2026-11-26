# Project status

**Last updated:** 2026-11-26
**Current stage:** 3. Marts (star schema)

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
  and the D-016 2 % income validation (+0.47 … +0.99 % in 2011–2025). D-028 proposed.

## Next steps (towards the dashboard)
1. Group aggregates (D-016): G4 / Rest of NL (+ secondary split) price, income and PTI per year.
2. `make export`: marts → Parquet in `data/processed/marts/` for Power BI.
3. Stage 4 (short EDA notebook) in parallel with stage 5 (Power BI), so the dashboard carries findings.

## Open items
- Owner: `make setup-geo && make geo` on the Mac (PDOK), then commit `data/reference/municipalities_2026.*`.
- Owner: `make lock` on the Mac (P-6: the lock was generated on Linux / Python 3.13).
- PDOK licence (D-014) — confirm before committing the boundary file.
- Historical mortgage-rate series (D-013, stretch) — owner downloads from DNB manually.
- End of project: "defend your decisions" walkthrough of D-001…D-027 with the owner.

## Key facts (do not re-derive)
- Years covered: 2011–2025; 2025 income preliminary (`Perioden.Status = 'Voorlopig'`).
- Municipality list version: gemeentelijke indeling 2026 (342 municipalities, `86247NED`).
- G4 codes: GM0363 Amsterdam, GM0599 Rotterdam, GM0518 's-Gravenhage, GM0344 Utrecht.
- Randstad provinces (secondary split): PV26 Utrecht, PV27 Noord-Holland, PV28 Zuid-Holland.
- Group PTI is never the mean of municipal PTIs (D-016).
