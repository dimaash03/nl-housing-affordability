-- 86380NED is published in the 2026 division: every year x household group must contain
-- exactly the 342 municipalities of stg_cbs__municipalities_2026 (no more, no fewer).
with income_gm as (
    select distinct year, household_group, region_code
    from staging.stg_cbs__household_income
    where region_type = 'GM'
),

expected as (
    select y.year, g.household_group, m.municipality_code as region_code
    from (select distinct year from staging.stg_cbs__household_income) as y
    cross join (select distinct household_group from staging.stg_cbs__household_income) as g
    cross join staging.stg_cbs__municipalities_2026 as m
)

select 'missing in income' as issue, * from (select * from expected except select * from income_gm)
union all
select 'not in 2026 list', * from (select * from income_gm except select * from expected)
