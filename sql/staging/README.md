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
