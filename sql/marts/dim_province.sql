-- dim_province
-- Source:  staging.stg_cbs__municipalities_2026 (86247NED, 2026 division)
--          reference.project_settings           (config/cbs_tables.yaml: randstad_provinces)
-- Grain:   one row per province_code (PVxx) -> 12 rows.
-- Filters: none.
-- Notes:   the province of each municipality is taken from the 2026 division, so every historical
--          year is shown in today's provinces (same convention as the municipality harmonisation).
--          is_randstad_province marks PV26 Utrecht, PV27 Noord-Holland, PV28 Zuid-Holland (D-010),
--          read from config/cbs_tables.yaml `randstad_provinces`.

with

municipalities as (
    select * from staging.stg_cbs__municipalities_2026
)

select
    m.province_code,
    m.province_name,
    list_contains(any_value(s.randstad_province_codes), m.province_code)  as is_randstad_province,
    count(*)                                                             as municipality_count_2026,
    sum(m.population)                                                    as population_2026
from municipalities as m
cross join reference.project_settings as s
group by m.province_code, m.province_name
order by m.province_code
