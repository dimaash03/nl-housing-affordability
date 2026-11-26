-- dim_year
-- Source:  staging.stg_cbs__household_income (86380NED, period status per year)
-- Grain:   one row per year of the analysis window 2011-2025 -> 15 rows (same spine as fct_affordability).
-- Filters: analysis window 2011-2025 (D-008).
-- Decisions:
--   D-008  is_preliminary comes from the CBS period status of the income table, never from the year.
--          The dashboard marks preliminary years with an asterisk (year_label) and every headline is
--          re-checked on latest_final_year.

with

years as (
    select unnest(range(2011, 2026))::integer as year
),

-- NL01 row of the income table: one status per year (the same for every region).
income_status as (
    select
        year,
        bool_or(is_preliminary) as is_preliminary
    from staging.stg_cbs__household_income
    where region_type = 'NL'
    group by year
),

joined as (
    select
        y.year,
        coalesce(s.is_preliminary, false)    as is_preliminary,
        s.year is not null                   as has_income_data
    from years as y
    left join income_status as s
        on s.year = y.year
)

select
    year,
    case when is_preliminary then year::varchar || '*' else year::varchar end  as year_label,
    is_preliminary,
    has_income_data,
    year - 2011                                                                as years_since_base,
    year = max(year) over ()                                                   as is_latest_year,
    year = max(case when has_income_data and not is_preliminary then year end) over ()
                                                                               as is_latest_final_year
from joined
order by year
