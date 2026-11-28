# Marts layer (`marts` schema)

Purpose: the business-facing star schema consumed by the notebooks and Power BI.
Built only from `staging` models and `reference` (herindeling mapping, `project_settings`) — never directly from `raw`.
The analysis window and the group lists come from `config/cbs_tables.yaml` via `reference.project_settings` (D-031).

Models (built by `make transform`, order in `sql/models.yaml`):

| Model | Grain | Rows | Description |
|---|---|---:|---|
| `fct_affordability` | municipality (2026) × year 2011–2025 | 5 130 | price, income, PTI, real values, growth, flags, rank |
| `dim_municipality` | municipality (GM code, 2026 division) | 342 | name, province, COROP, `is_g4`, `region_group`, `region_group_3` (+ sort key), urbanity and size class, population 2026 |
| `dim_province` | province (PV code) | 12 | name, `is_randstad_province`, municipality count, population 2026 |
| `dim_year` | year 2011–2025 | 15 | `year_label` (`2025*` when preliminary), `is_preliminary`, `has_*_data`, `municipalities_with_pti`, `is_latest_data_year`, `is_latest_final_year` (D-030) |
| `fct_group_affordability` | group_type × group_code × year | 270 | NL, 12 provinces, G4 / Rest of NL, G4 / Rest of Randstad provinces / Rest of NL: price, income, PTI, growth, `price_method` / `income_method` / `is_income_approximated` (D-016, D-029) |

Relationships (Power BI, single direction): `fct_affordability[municipality_code]` → `dim_municipality`,
`fct_affordability[year]` → `dim_year`. `fct_group_affordability` is a separate fact (no relationship to `dim_municipality`); relate it to `dim_year` and slice on `group_type`.
Municipality slicers use the province columns denormalised in `dim_municipality` (D-028).

Integrity is tested by `sql/tests/assert_marts_grain_and_keys.sql` (grain, uniqueness, orphan keys, G4 list),
`assert_dimensions_match_source.sql` (codes and names vs raw 86247NED and the province / municipality labels of
the other CBS tables), `assert_region_groups.sql` (D-010 rules as literals, group sizes 4 / 116 / 222, method labels,
households add up), `assert_income_weighted_median_vs_nl.sql` (D-016 2 % validation), `assert_group_aggregates.sql`
and `assert_project_settings.sql`.
`make export` writes every table to `data/processed/marts/<table>.parquet` for Power BI.

Naming conventions:
- facts `fct_<subject>`, dimensions `dim_<entity>`; file name = table name (`fct_affordability.sql`)
- surrogate-free keys: use CBS codes (`municipality_code = 'GM0363'`) and `year` (integer)
- CTEs, snake_case, units in column names (`avg_sale_price_eur`, `price_to_income_ratio`)
- every metric's definition is documented in `docs/DATA_DICTIONARY.md` and its rationale in `docs/DECISIONS_LOG.md`
