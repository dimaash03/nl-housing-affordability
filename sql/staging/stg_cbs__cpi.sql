-- stg_cbs__cpi
-- Source:  CBS 86141NED "Consumentenprijzen; CPI 2025=100, index en mutaties" (raw.cbs_86141ned)
-- Grain:   one row per year
-- Filters: Bestedingscategorieen = 'T001112' after TRIM (raw key is 'T001112  ' = all expenditure);
--          yearly averages only (YYYYJJ00), monthly rows dropped
-- Notes:
--   - Used as the deflator to express euro amounts in 2025 prices (D-005): real = nominal * 100 / cpi.
--   - cpi_yoy_pct is CBS's own published year-on-year change, not recomputed.

with source as (
    select * from raw.cbs_86141ned
),

renamed as (
    select
        trim(Bestedingscategorieen)      as expenditure_category_code,
        trim(Perioden)                   as period_code,
        CPI_1                            as cpi_2025_index,
        JaarmutatieCPI_5                 as cpi_yoy_pct
    from source
)

select
    cast(left(period_code, 4) as integer) as year,
    cpi_2025_index,
    cpi_yoy_pct
from renamed
where expenditure_category_code = 'T001112'
  and substr(period_code, 5, 2) = 'JJ'
