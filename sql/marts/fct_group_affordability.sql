-- fct_group_affordability
-- Source:  staging.stg_cbs__house_prices        (83625NED, published NL / province average prices)
--          staging.stg_cbs__house_price_index   (85792NED, transaction counts + average prices for NL01,
--                                                the 12 provinces and the 4 G4 cities)
--          staging.stg_cbs__household_income    (86380NED, published NL / province medians)
--          marts.fct_affordability              (municipal medians and household counts, 2026 division)
--          marts.dim_municipality               (region groups, D-010)
--          staging.stg_cbs__cpi                 (86141NED, CPI 2025 = 100)
--          reference.project_settings           (config/cbs_tables.yaml: analysis window, base year)
-- Grain:   one row per group_type x group_code x year of the analysis window (2011-2025):
--            nl (1) + province (12) + region_group (G4, Rest of NL) + region_group_3 (G4,
--            Rest of Randstad provinces, Rest of NL) = 18 groups x 15 years = 270 rows.
-- Filters: analysis window year_from..year_to from reference.project_settings (D-008).
-- Decisions:
--   D-016  A group PTI is group price / group income, NEVER the mean of municipal PTIs.
--          Price: published CBS row where one exists (NL, province); G4 = transaction-weighted mean of
--          the four cities; Rest of NL = exact residual NL minus G4 (sum of price x count).
--          Income: published CBS median where one exists; otherwise the household-weighted mean of
--          municipal medians (approximation, bounded by assert_income_weighted_median_vs_nl.sql).
--   D-029  Rest of Randstad provinces price = exact residual (PV26 + PV27 + PV28) minus G4 with
--          85792NED counts, instead of the owner-stock-weighted approximation planned in D-016.
--   Territory: 85792NED reports each year in that year's boundaries, so the G4 price excludes Weesp
--          before 2022 (Weesp sits in Rest of NL / Rest of Randstad provinces until it joined Amsterdam).
--          Group incomes use the 2026 division. Documented as a limitation (Weesp < 0.2 % of households).
--   D-034 / D-038  Owner-occupier income (the mandatory sensitivity, D-003) is built the same way as the main
--          income: published CBS owner-occupier median for NL and provinces; otherwise the mean of municipal
--          owner-occupier medians weighted by owner-occupier households (approximation, bounded by
--          assert_owner_income_weighted_median_vs_nl.sql). Moved here from the notebook for the dashboard's
--          income-basis switch.

with

settings as (
    select year_from, year_to, base_year
    from reference.project_settings
),

years as (
    select unnest(range(year_from, year_to + 1))::integer as year
    from settings
),

-- 1. Transactions and mean prices from 85792NED. The residual formula needs price and count from the
--    SAME table so that sum(price x count) is internally consistent.
tx as (
    select region_code, year, avg_sale_price_eur, transactions_count
    from staging.stg_cbs__house_price_index
    where year in (select year from years)
),

g4_tx as (
    select
        year,
        sum(avg_sale_price_eur * transactions_count)   as price_x_count,
        sum(transactions_count)                         as transactions_count
    from tx
    where region_code in (select municipality_code from marts.dim_municipality where is_g4)
    group by year
),

randstad_tx as (
    select
        year,
        sum(avg_sale_price_eur * transactions_count)   as price_x_count,
        sum(transactions_count)                         as transactions_count
    from tx
    where region_code in (select province_code from marts.dim_province where is_randstad_province)
    group by year
),

nl_tx as (
    select
        year,
        avg_sale_price_eur * transactions_count         as price_x_count,
        transactions_count
    from tx
    where region_code = 'NL01'
),

-- 2. Group prices.
prices as (
    -- NL and provinces: the published CBS average (83625NED).
    select
        case when region_type = 'NL' then 'nl' else 'province' end  as group_type,
        region_code                                                  as group_code,
        year,
        avg_sale_price_eur,
        'cbs_published'                                              as price_method
    from staging.stg_cbs__house_prices
    where region_type in ('NL', 'PV')
      and year in (select year from years)

    union all
    -- G4 combined: transaction-weighted mean (two-way and three-way split share the value).
    select gt.group_type, 'G4', g.year,
           g.price_x_count / g.transactions_count, 'transaction_weighted'
    from g4_tx as g
    cross join (values ('region_group'), ('region_group_3')) as gt(group_type)

    union all
    -- Rest of NL (two-way split): exact residual NL minus G4.
    select 'region_group', 'REST_NL', n.year,
           (n.price_x_count - g.price_x_count) / (n.transactions_count - g.transactions_count),
           'exact_residual'
    from nl_tx as n
    join g4_tx as g using (year)

    union all
    -- Rest of Randstad provinces: exact residual (PV26 + PV27 + PV28) minus G4 (D-029).
    select 'region_group_3', 'REST_RANDSTAD', r.year,
           (r.price_x_count - g.price_x_count) / (r.transactions_count - g.transactions_count),
           'exact_residual'
    from randstad_tx as r
    join g4_tx as g using (year)

    union all
    -- Rest of NL (three-way split): exact residual NL minus the three Randstad provinces.
    select 'region_group_3', 'REST_NL', n.year,
           (n.price_x_count - r.price_x_count) / (n.transactions_count - r.transactions_count),
           'exact_residual'
    from nl_tx as n
    join randstad_tx as r using (year)
),

-- Transaction counts per group, for context and weighting in the dashboard.
transactions as (
    select 'nl' as group_type, 'NL01' as group_code, year, transactions_count from nl_tx
    union all
    select 'province', region_code, year, transactions_count from tx where region_code like 'PV%'
    union all
    select gt.group_type, 'G4', year, transactions_count
    from g4_tx cross join (values ('region_group'), ('region_group_3')) as gt(group_type)
    union all
    select 'region_group', 'REST_NL', n.year, n.transactions_count - g.transactions_count
    from nl_tx as n join g4_tx as g using (year)
    union all
    select 'region_group_3', 'REST_RANDSTAD', r.year, r.transactions_count - g.transactions_count
    from randstad_tx as r join g4_tx as g using (year)
    union all
    select 'region_group_3', 'REST_NL', n.year, n.transactions_count - r.transactions_count
    from nl_tx as n join randstad_tx as r using (year)
),

-- 3. Group incomes.
municipal_income as (
    select
        f.year,
        f.median_disposable_income_eur,
        f.households_count,
        f.is_preliminary,
        d.region_group,
        d.region_group_3
    from marts.fct_affordability as f
    join marts.dim_municipality as d using (municipality_code)
    where not f.income_missing
),

incomes as (
    -- NL and provinces: the published CBS median (86380NED, 2026 division).
    select
        case when region_type = 'NL' then 'nl' else 'province' end  as group_type,
        region_code                                                  as group_code,
        year,
        median_disposable_income_eur,
        households_count,
        is_preliminary,
        'cbs_published'                                              as income_method
    from staging.stg_cbs__household_income
    where region_type in ('NL', 'PV')
      and household_group = 'all'
      and year in (select year from years)

    union all
    -- Region groups: household-weighted mean of municipal medians (approximation, D-016).
    select
        'region_group',
        case region_group when 'G4' then 'G4' else 'REST_NL' end,
        year,
        sum(median_disposable_income_eur * households_count) / sum(households_count),
        sum(households_count),
        bool_or(is_preliminary),
        'household_weighted_median'
    from municipal_income
    group by all

    union all
    select
        'region_group_3',
        case region_group_3
            when 'G4' then 'G4'
            when 'Rest of Randstad provinces' then 'REST_RANDSTAD'
            else 'REST_NL'
        end,
        year,
        sum(median_disposable_income_eur * households_count) / sum(households_count),
        sum(households_count),
        bool_or(is_preliminary),
        'household_weighted_median'
    from municipal_income
    group by all
),

-- 3b. Owner-occupier group incomes (D-034, D-038). Separate from `incomes` so that a municipality with an
--     owner-occupier median but no all-household median (or the reverse) is weighted on its own basis.
municipal_owner_income as (
    select
        f.year,
        f.median_disposable_income_owner_eur,
        f.owner_households_count,
        d.region_group,
        d.region_group_3
    from marts.fct_affordability as f
    join marts.dim_municipality as d using (municipality_code)
    where f.median_disposable_income_owner_eur is not null
      and f.owner_households_count is not null
),

owner_incomes as (
    select
        case when region_type = 'NL' then 'nl' else 'province' end  as group_type,
        region_code                                                  as group_code,
        year,
        median_disposable_income_eur                                 as median_disposable_income_owner_eur,
        households_count                                             as owner_households_count,
        'cbs_published'                                              as income_owner_method
    from staging.stg_cbs__household_income
    where region_type in ('NL', 'PV')
      and household_group = 'owner_occupier'
      and year in (select year from years)

    union all
    select
        'region_group',
        case region_group when 'G4' then 'G4' else 'REST_NL' end,
        year,
        sum(median_disposable_income_owner_eur * owner_households_count) / sum(owner_households_count),
        sum(owner_households_count),
        'owner_household_weighted_median'
    from municipal_owner_income
    group by all

    union all
    select
        'region_group_3',
        case region_group_3
            when 'G4' then 'G4'
            when 'Rest of Randstad provinces' then 'REST_RANDSTAD'
            else 'REST_NL'
        end,
        year,
        sum(median_disposable_income_owner_eur * owner_households_count) / sum(owner_households_count),
        sum(owner_households_count),
        'owner_household_weighted_median'
    from municipal_owner_income
    group by all
),

-- 4. Names and sort order of the groups (provinces from dim_province).
groups as (
    select 'nl' as group_type, 'NL01' as group_code, 'Netherlands' as group_name, 0 as group_sort
    union all
    select 'province', province_code, province_name, row_number() over (order by province_code)::integer
    from marts.dim_province
    union all
    select * from (values
        ('region_group',   'G4',            'G4',                          1),
        ('region_group',   'REST_NL',       'Rest of NL',                  2),
        ('region_group_3', 'G4',            'G4',                          1),
        ('region_group_3', 'REST_RANDSTAD', 'Rest of Randstad provinces',  2),
        ('region_group_3', 'REST_NL',       'Rest of NL',                  3)
    ) as t(group_type, group_code, group_name, group_sort)
),

-- 5. Spine: every group x every year, so a missing input is a visible NULL, never a lost row.
joined as (
    select
        g.group_type,
        g.group_code,
        g.group_name,
        g.group_sort,
        y.year,
        p.avg_sale_price_eur,
        p.price_method,
        t.transactions_count,
        i.median_disposable_income_eur,
        i.income_method,
        i.households_count,
        coalesce(i.is_preliminary, false)   as is_preliminary,
        o.median_disposable_income_owner_eur,
        o.owner_households_count,
        o.income_owner_method,
        c.cpi_2025_index
    from groups as g
    cross join years as y
    left join prices as p
        on p.group_type = g.group_type and p.group_code = g.group_code and p.year = y.year
    left join transactions as t
        on t.group_type = g.group_type and t.group_code = g.group_code and t.year = y.year
    left join incomes as i
        on i.group_type = g.group_type and i.group_code = g.group_code and i.year = y.year
    left join owner_incomes as o
        on o.group_type = g.group_type and o.group_code = g.group_code and o.year = y.year
    left join staging.stg_cbs__cpi as c
        on c.year = y.year
),

metrics as (
    select
        *,
        avg_sale_price_eur / median_disposable_income_eur                          as price_to_income_ratio,
        avg_sale_price_eur / median_disposable_income_owner_eur                    as price_to_income_owner_ratio,
        avg_sale_price_eur * 100 / cpi_2025_index                                  as real_avg_sale_price_eur_2025,
        median_disposable_income_eur * 100 / cpi_2025_index                        as real_median_disposable_income_eur_2025,
        (avg_sale_price_eur
            / max(case when year = (select base_year from settings) then avg_sale_price_eur end)
                  over (partition by group_type, group_code) - 1) * 100            as price_growth_since_2011_pct,
        (median_disposable_income_eur
            / max(case when year = (select base_year from settings) then median_disposable_income_eur end)
                  over (partition by group_type, group_code) - 1) * 100            as income_growth_since_2011_pct
    from joined
)

select
    group_type,
    group_code,
    group_name,
    group_sort,
    -- one sort value per group_name (group_sort repeats 'Rest of NL' as 2 and 3), so Power BI can use it as
    -- the sort-by column of group_name: Netherlands, G4, Rest of Randstad provinces, Rest of NL, provinces
    case
        when group_type = 'nl'       then 0
        when group_type = 'province' then 10 + group_sort
        else case group_code when 'G4' then 1 when 'REST_RANDSTAD' then 2 else 3 end
    end::integer                                                as group_name_sort,
    year,
    avg_sale_price_eur,
    median_disposable_income_eur,
    price_to_income_ratio,
    median_disposable_income_owner_eur,
    price_to_income_owner_ratio,
    transactions_count,
    households_count,
    owner_households_count,
    cpi_2025_index,
    real_avg_sale_price_eur_2025,
    real_median_disposable_income_eur_2025,
    price_growth_since_2011_pct,
    income_growth_since_2011_pct,
    price_growth_since_2011_pct - income_growth_since_2011_pct  as growth_gap_pp,
    price_method,
    income_method,
    -- true where the group income is the household-weighted mean of municipal medians (G4 / Rest groups),
    -- not a published CBS median; bounded at NL level by assert_income_weighted_median_vs_nl.sql (D-016)
    income_method <> 'cbs_published'                            as is_income_approximated,
    income_owner_method,
    is_preliminary
from metrics
order by group_type, group_sort, year
