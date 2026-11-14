# Power BI

What will live here:
- `nl_housing_affordability.pbix` — the dashboard (committed; it contains no credentials);
- `screenshots/` — images used in the main README;
- notes on DAX measures, if they are not self-explanatory in the model.

## How the report connects to the data

The pipeline runs on macOS; Power BI Desktop runs in a Windows VM. To avoid installing a database
server or ODBC driver on the Windows side:

1. The `marts` tables in DuckDB are exported to Parquet in `data/processed/marts/`
   (export step to be added to the pipeline; `COPY marts.<table> TO '...parquet' (FORMAT parquet)`).
2. The repo folder is shared with the VM (e.g. a Parallels/UTM shared folder).
3. Power BI imports each Parquet file with Power Query (`Parquet.Document(File.Contents(...))`),
   using a single **parameter** for the base folder so the path is not hardcoded in every query.

Alternative if live access is ever needed: the DuckDB ODBC driver on Windows.

## Model

Star schema in Import mode: `fct_affordability` (municipality × year) related many-to-one to
`dim_municipality`, `dim_year` and (via municipality) `dim_province`. Single-direction filters.
