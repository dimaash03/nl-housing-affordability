-- From 2023 the price table uses the same 342 municipalities as the 2026 division,
-- so each of 2023-2025 must have exactly 342 GM rows with a price.
with gm_per_year as (
    select year, count(*) as gm_count
    from staging.stg_cbs__house_prices
    where region_type = 'GM'
      and year between 2023 and 2025
    group by year
),

expected_years as (
    select unnest(range(2023, 2026)) as year
)

select e.year, coalesce(g.gm_count, 0) as gm_count
from expected_years as e
left join gm_per_year as g using (year)
where coalesce(g.gm_count, 0) <> 342
