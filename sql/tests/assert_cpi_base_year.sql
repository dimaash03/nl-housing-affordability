-- 86141NED is based 2025 = 100: the yearly average for 2025 must be exactly 100,
-- and every year of the analysis window 2011-2025 must be present.
with expected_years as (
    select unnest(range(2011, 2026)) as year
)

select e.year, c.cpi_2025_index
from expected_years as e
left join staging.stg_cbs__cpi as c using (year)
where c.cpi_2025_index is null
   or (e.year = 2025 and c.cpi_2025_index <> 100)
