-- D-034 / D-038 validation: the owner-occupier-household-weighted mean of the municipal owner-occupier
-- medians must stay within 2 % of the official NL owner-occupier median (NL01, Kenmerk 1014800 of 86380NED)
-- in every year. It is the approximation used for the owner-occupier income of the G4 and Rest groups in
-- marts.fct_group_affordability; this test bounds its error at country level, like the D-016 test does
-- for the all-household income (assert_income_weighted_median_vs_nl.sql).
-- Municipality-years without an owner-occupier median or owner household count are left out.
-- Returns one row per year outside the tolerance (or without a published NL value).
with

weighted as (
    select
        year,
        sum(median_disposable_income_owner_eur * owner_households_count)
            / sum(owner_households_count)                       as weighted_median_eur
    from marts.fct_affordability
    where median_disposable_income_owner_eur is not null
      and owner_households_count is not null
    group by year
),

official as (
    select year, median_disposable_income_eur as nl_owner_median_eur
    from staging.stg_cbs__household_income
    where region_type = 'NL' and household_group = 'owner_occupier'
),

compared as (
    select
        w.year,
        w.weighted_median_eur,
        o.nl_owner_median_eur,
        (w.weighted_median_eur / o.nl_owner_median_eur - 1) * 100   as diff_pct
    from weighted as w
    left join official as o using (year)
)

select *
from compared
where nl_owner_median_eur is null
   or abs(diff_pct) > 2
order by year
