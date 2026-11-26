-- dim_province
-- Source:  staging.stg_cbs__municipalities_2026 (86247NED, 2026 division)
-- Grain:   one row per province_code (PVxx) -> 12 rows.
-- Filters: none.
-- Notes:   the province of each municipality is taken from the 2026 division, so every historical
--          year is shown in today's provinces (same convention as the municipality harmonisation).
--          is_randstad_province marks PV26 Utrecht, PV27 Noord-Holland, PV28 Zuid-Holland (D-010).

with

municipalities as (
    select * from staging.stg_cbs__municipalities_2026
)

select
    province_code,
    province_name,
    province_code in ('PV26', 'PV27', 'PV28')     as is_randstad_province,
    count(*)                                       as municipality_count_2026,
    sum(population)                                as population_2026
from municipalities
group by province_code, province_name
order by province_code
