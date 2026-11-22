-- The 2025 price rows (reporting-year boundaries) must use exactly the 2026 municipality codes.
-- If CBS adds a herindeling effective 1 January 2026 this fails and the mapping must cover 2025 too.
with prices_2025 as (
    select region_code from staging.stg_cbs__house_prices where region_type = 'GM' and year = 2025
),

municipalities as (
    select municipality_code as region_code from staging.stg_cbs__municipalities_2026
)

select 'in prices 2025, not in 2026 list' as issue, region_code
from (select * from prices_2025 except select * from municipalities)
union all
select 'in 2026 list, no price in 2025', region_code
from (select * from municipalities except select * from prices_2025)
