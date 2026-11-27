# CLAUDE.md — conventions for AI agents and future sessions

## Project
Housing affordability (house price vs household income) per Dutch municipality, ~last 10+ years,
Randstad (G4: Amsterdam, Rotterdam, Den Haag, Utrecht) vs rest of NL. Portfolio project for the Dutch data-analyst market.
Pipeline: CBS OData → Python → DuckDB (raw → staging → marts) → notebooks + Power BI (star schema).

## Where things live
- `config/cbs_tables.yaml` — tables to ingest (example: `cbs_tables.example.yaml`, used only as fallback)
- `src/nl_housing/` — `config.py` (paths, config parsing), `ingest.py`, `load_duckdb.py`, `transform.py` (SQL runner),
  `check.py` (SQL data tests), `geo.py` (PDOK boundaries)
- `sql/models.yaml` — execution order of the SQL models; `sql/tests/` — data tests (`make check`)
- `data/reference/` — small committed reference files (boundaries, herindeling mapping)
- `data/raw/<table_id>/` — Parquet + `metadata.json` (gitignored); `data/nl_housing.duckdb` (gitignored)
- `sql/staging/` (`stg_*`), `sql/marts/` (`fct_*`, `dim_*`) — see each README
- `notebooks/` — EDA/analysis; `powerbi/` — .pbix + notes; `tests/` — offline pytest
- `docs/PROJECT_STATUS.md` — **current stage and next steps (read first, update when done)**
- `docs/DATA_DICTIONARY.md`, `docs/DECISIONS_LOG.md`, `docs/cbs_tables_research.md` — data + decisions

## Hard rules
- All repo content in **English** (code, comments, docs, commit messages).
- **Never fabricate numbers, results or table ids.** Every figure must come from a query/notebook in the repo.
  Verify CBS table ids against the catalog (`https://opendata.cbs.nl/ODataCatalog/Tables?$format=json`).
- The owner must be able to **defend every decision**: explain choices in the PR/commit and log
  significant ones in `docs/DECISIONS_LOG.md` (what, why, alternatives considered).
- Never commit data files, `.duckdb` files or secrets.
- Raw layer is never edited; cleaning happens in staging SQL.

## SQL style
- DuckDB dialect; one model per file, file name = table name.
- CTEs over subqueries; snake_case; English column names with units (`_eur`, `_pct`, `_index`).
- Prefixes: `stg_<source>__<entity>`, `fct_<subject>`, `dim_<entity>`.
- `TRIM()` CBS dimension codes (they are space-padded); keys = CBS codes (`GM0363`) and integer `year`.
- Header comment: source, grain, filters.

## Python style
- Python 3.11+ (DuckDB 2.x), type hints, docstrings, `logging` (no `print` in library code).
- `pathlib` paths relative to `config.REPO_ROOT`; no absolute paths.
- CLIs via `python -m nl_housing.<module>`; keep steps idempotent.
- Tests must run offline (mock HTTP, use `tmp_path`); run `make test` before committing.

## Workflow
- Small, logical commits with clear messages; don't force-push shared branches.
- Update `docs/PROJECT_STATUS.md` (date, stage, done, next) at the end of each work session.
