# Marts layer (`marts` schema)

Purpose: the business-facing star schema consumed by the notebooks and Power BI.
Built only from `staging` models — never directly from `raw`.

Models (built by `make transform`, order in `sql/models.yaml`):

| Model | Grain | Rows | Description |
|---|---|---:|---|
| `fct_affordability` | municipality (2026) × year 2011–2025 | 5 130 | price, income, PTI, real values, growth, flags, rank |
| `dim_municipality` | municipality (GM code, 2026 division) | 342 | name, province, COROP, `is_g4`, `region_group`, `region_group_3` (+ sort key), urbanity and size class, population 2026 |
| `dim_province` | province (PV code) | 12 | name, `is_randstad_province`, municipality count, population 2026 |
| `dim_year` | year 2011–2025 | 15 | `year_label` (`2025*` when preliminary), `is_preliminary`, `is_latest_year`, `is_latest_final_year` |

Relationships (Power BI, single direction): `fct_affordability[municipality_code]` → `dim_municipality`,
`fct_affordability[year]` → `dim_year`. `dim_province` filters province-level facts (group aggregates, planned);
municipality slicers use the province columns denormalised in `dim_municipality` (D-028).

Integrity is tested by `sql/tests/assert_marts_grain_and_keys.sql` (grain, uniqueness, orphan keys, G4 list)
and `sql/tests/assert_income_weighted_median_vs_nl.sql` (D-016 2 % validation).

Naming conventions:
- facts `fct_<subject>`, dimensions `dim_<entity>`; file name = table name (`fct_affordability.sql`)
- surrogate-free keys: use CBS codes (`municipality_code = 'GM0363'`) and `year` (integer)
- CTEs, snake_case, units in column names (`avg_sale_price_eur`, `price_to_income_ratio`)
- every metric's definition is documented in `docs/DATA_DICTIONARY.md` and its rationale in `docs/DECISIONS_LOG.md`
