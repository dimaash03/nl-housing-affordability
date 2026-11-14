# Project status

**Last updated:** 2026-11-14
**Current stage:** 1. Scoping / data sourcing

Stages: 1. Scoping / data sourcing → 2. Ingestion & staging → 3. Marts (star schema) → 4. Analysis (notebooks) → 5. Power BI dashboard → 6. Write-up (README insights, limitations).

## Done
- Project skeleton: folder structure, README, CLAUDE.md, Makefile, requirements, `.gitignore`.
- `nl_housing.ingest`: generic, idempotent CBS OData downloader (dataset + DataProperties + TableInfos +
  CategoryGroups + dimension code tables → Parquet, plus `metadata.json` with provenance).
- `nl_housing.load_duckdb`: loads `data/raw/` into `data/nl_housing.duckdb`, schema `raw`
  (`raw.cbs_<id>`, `raw.cbs_<id>__dim_<dimension>`, `raw._ingest_log`).
- Offline unit tests (config parsing, output paths, ingest with mocked HTTP, DuckDB load).
- Live smoke test (2026-11-14): ingested CBS tables `85773NED` (via the example config) and `83625NED`
  (ad hoc, >10k rows to exercise pagination) and loaded both into DuckDB successfully. No data committed.

## Next steps
1. Review the researcher's PR (`docs/DATA_DICTIONARY.md`, `docs/cbs_tables_research.md`,
   `docs/DECISIONS_LOG.md`, `config/cbs_tables.yaml`).
2. Approve metric definitions (house price measure, income measure, affordability ratio).
3. Run `make ingest && make load` for the verified tables.
4. Build the first staging models in `sql/staging/` (plus a small runner to execute the SQL files in order).

## Open questions
- Which income measure: mean vs. median, disposable vs. standardised household income — and at what geographic level is it available per year?
- Exact time window (depends on the overlapping years of the price and income tables).
- How to handle municipal mergers (*herindelingen*): map history to the current municipality boundaries, or analyse per-year boundaries?
- Randstad definition: G4 only (as scoped) or the wider Randstad as a sensitivity check?
- Power BI refresh: Parquet export from DuckDB (planned) vs. DuckDB ODBC driver.
