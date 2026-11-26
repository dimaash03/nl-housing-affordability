-- D-016 validation: the household-weighted mean of the 342 municipal median incomes must stay within
-- 2 % of the official NL median (NL01 row of 86380NED) in every year. The weighted mean of medians is
-- the approximation used for group income (G4, Rest of NL); this test bounds its error at country level.
-- Municipality-years without income (income_missing) are left out of numerator and denominator.
-- Returns one row per year outside the tolerance.
with

weighted as (
    select
        year,
        sum(median_disposable_income_eur * households_count) / sum(households_count)  as weighted_median_eur
    from marts.fct_affordability
    where not income_missing
    group by year
),

official as (
    select year, median_disposable_income_eur as nl_median_eur
    from staging.stg_cbs__household_income
    where region_type = 'NL' and household_group = 'all'
),

compared as (
    select
        w.year,
        w.weighted_median_eur,
        o.nl_median_eur,
        (w.weighted_median_eur / o.nl_median_eur - 1) * 100   as diff_pct
    from weighted as w
    left join official as o using (year)
)

select *
from compared
where nl_median_eur is null
   or abs(diff_pct) > 2
order by year
