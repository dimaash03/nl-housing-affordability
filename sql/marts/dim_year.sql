-- dim_year
-- Source:  reference.project_settings        (config/cbs_tables.yaml `project:`: analysis window, base year)
--          staging.stg_cbs__household_income (86380NED, CBS period status per year)
--          marts.fct_affordability           (which years actually have price, income and PTI data)
-- Grain:   one row per year of the analysis window -> 15 rows for 2011-2025 (same spine as fct_affordability).
-- Filters: analysis window year_from..year_to (D-008).
-- Decisions:
--   D-008  is_preliminary comes from the CBS period status of the income table, never from the year.
--          The dashboard marks preliminary years with an asterisk (year_label) and every headline is
--          re-checked on the latest final year.
--   D-030  (proposed) "latest" flags are based on loaded data, not on the configured window:
--          is_latest_data_year  = last year with a PTI for at least one municipality;
--          is_latest_final_year = last such year whose income is final (not 'Voorlopig').
--          A year that is configured but not (yet) published or loaded is still a row (the spine), but
--          has_pti_data = false and it can never be "latest". Replaces is_latest_year (= max of the window).

with

settings as (
    select year_from, year_to, base_year
    from reference.project_settings
),

years as (
    select unnest(range(year_from, year_to + 1))::integer as year
    from settings
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

-- What the fact table really contains per year (counts are over the 342 municipalities of 2026).
fact_coverage as (
    select
        year,
        count(avg_sale_price_eur)            as municipalities_with_price,
        count(median_disposable_income_eur)  as municipalities_with_income,
        count(price_to_income_ratio)         as municipalities_with_pti
    from marts.fct_affordability
    group by year
),

joined as (
    select
        y.year,
        coalesce(s.is_preliminary, false)             as is_preliminary,
        coalesce(c.municipalities_with_price, 0)      as municipalities_with_price,
        coalesce(c.municipalities_with_income, 0)     as municipalities_with_income,
        coalesce(c.municipalities_with_pti, 0)        as municipalities_with_pti
    from years as y
    left join income_status as s
        on s.year = y.year
    left join fact_coverage as c
        on c.year = y.year
),

flags as (
    select
        *,
        municipalities_with_price > 0   as has_price_data,
        municipalities_with_income > 0  as has_income_data,
        municipalities_with_pti > 0     as has_pti_data
    from joined
)

select
    year,
    case when is_preliminary then year::varchar || '*' else year::varchar end  as year_label,
    is_preliminary,
    has_price_data,
    has_income_data,
    has_pti_data,
    municipalities_with_pti,
    year - (select base_year from settings)                                    as years_since_base,
    coalesce(year = max(case when has_pti_data then year end) over (), false)  as is_latest_data_year,
    coalesce(year = max(case when has_pti_data and not is_preliminary then year end) over (), false)
                                                                               as is_latest_final_year
from flags
order by year
