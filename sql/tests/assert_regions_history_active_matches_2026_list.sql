-- Municipalities without an end date in 70739ned must be exactly the 342 of the 2026 division.
-- GM0998 'Buitenland' (abroad) is a CBS pseudo-municipality used for border changes with other
-- countries; it never ends and is not a municipality, so it is excluded here (and must be ignored
-- by the herindeling parser).
with active as (
    select region_code
    from staging.stg_cbs__regions_history
    where region_type = 'GM'
      and end_date is null
      and region_code <> 'GM0998'
),

municipalities as (
    select municipality_code as region_code from staging.stg_cbs__municipalities_2026
)

select 'active in 70739ned, not in 2026 list' as issue, region_code
from (select * from active except select * from municipalities)
union all
select 'in 2026 list, ended in 70739ned', region_code
from (select * from municipalities except select * from active)
