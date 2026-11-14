# Marts layer (`marts` schema)

Purpose: the business-facing star schema consumed by the notebooks and Power BI.
Built only from `staging` models — never directly from `raw`.

Planned models:

| Model | Grain | Description |
|---|---|---|
| `fct_affordability` | municipality × year | house price, household income and derived affordability ratios |
| `dim_municipality` | municipality (GM code) | name, province, Randstad/G4 flag, current-boundary mapping |
| `dim_province` | province (PV code) | name |
| `dim_year` | year | calendar year attributes |

Naming conventions:
- facts `fct_<subject>`, dimensions `dim_<entity>`; file name = table name (`fct_affordability.sql`)
- surrogate-free keys: use CBS codes (`municipality_code = 'GM0363'`) and `year` (integer)
- CTEs, snake_case, units in column names (`avg_sale_price_eur`, `price_to_income_ratio`)
- every metric's definition is documented in `docs/DATA_DICTIONARY.md` and its rationale in `docs/DECISIONS_LOG.md`
