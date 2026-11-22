# Staging layer (`staging` schema)

Purpose: turn each raw CBS table (`raw.cbs_<id>`) into a clean, analysis-ready table.
One staging model per source table; **no business logic or joins across sources here**.

What happens in staging:
- rename CBS columns (`GemiddeldeVerkoopprijs_1`) to clear English snake_case (`avg_sale_price_eur`);
- `TRIM()` dimension codes — CBS pads codes such as `RegioS` with trailing spaces (`'NL01  '`);
- split region codes into type + code (`GM` = municipality, `PV` = province, `NL01` = country);
- parse `Perioden` (`2024JJ00` = year, `2024KW01` = quarter, `2024MM01` = month) into proper date / year columns;
- cast types, keep CBS status flags (provisional / revised) where available;
- keep units explicit in column names (`_eur`, `_eur_k`, `_pct`, `_index`).

Naming conventions:
- file = model = table: `stg_<source>__<entity>.sql`, e.g. `stg_cbs__house_prices.sql` → `staging.stg_cbs__house_prices`
- one `SELECT` per file, built from CTEs (`with source as (...), renamed as (...) select * from renamed`)
- snake_case everywhere, lowercase SQL keywords are fine but be consistent within a file
- a header comment in each file: source table id, grain, and any filters applied

## Models

Built by `make transform` in the order of [`../models.yaml`](../models.yaml); checked by `make check` ([`../tests/`](../tests)).
Row counts are from the run of 2026-11-22 (CBS data as downloaded that day).

| Model | Source | Grain | Main filters | Rows |
|---|---|---|---|---|
| `stg_cbs__house_prices` | 83625NED | region_code × year | yearly, year ≥ 2011, NULL price dropped | 5 884 |
| `stg_cbs__household_income` | 86380NED | region_code × year × household_group | Populatie 3000870; Kenmerk 1050010 (`all`) / 1014800 (`owner_occupier`) | 13 020 |
| `stg_cbs__regional_key_figures` | 70072ned | region_code × year | yearly, year ≥ 2011, all-NULL rows dropped | 6 882 |
| `stg_cbs__cpi` | 86141NED | year | category `T001112`, yearly averages | 16 |
| `stg_cbs__municipalities_2026` | 86247NED | municipality_code | none | 342 |
| `stg_cbs__house_price_index` | 85792NED | region_code × year | yearly (all years since 1995) | 651 |
| `stg_cbs__regions_history` | 70739ned | region_code | none | 1 531 |

Conventions used in every model:
- region codes trimmed; `region_type` = first two letters (`GM`, `PV`, `LD`, `NL`, plus `CR`/`AM` where CBS publishes them);
- `year` = integer from `YYYYJJ00`; non-yearly periods are dropped;
- CBS units converted: `1 000 euro` → euro (`_eur`), `x 1 000` households → count (`households_count`);
- historical GM codes are kept as published (reporting-year boundaries); mapping to 2026 happens downstream (D-007).
