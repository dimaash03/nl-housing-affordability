-- Group aggregates (D-016, D-029). Returns one row per violation.
--   - grain: 18 groups x n_years (15 for 2011-2025), unique on (group_type, group_code, year), no missing price / income
--   - the residual formula needs 85792NED and 83625NED to agree on the NL and province averages
--     (otherwise "NL minus G4" mixes two definitions); G4 cities may differ by a revision of < 0.1 %
--   - residual groups must have positive transaction counts
--   - G4 + Rest of NL transactions = NL; G4 + Rest of Randstad + Rest of NL (3-way) = NL
--   - G4 / Rest of NL price recombined with the counts gives back the NL price (catches a wrong residual)
with

grain as (
    select count(*) as n_rows, count(distinct group_type || '|' || group_code || '|' || year) as n_keys
    from marts.fct_group_affordability
),

consistency as (
    select i.region_code, i.year,
           abs(i.avg_sale_price_eur / p.avg_sale_price_eur - 1) * 100 as diff_pct
    from staging.stg_cbs__house_price_index as i
    join staging.stg_cbs__house_prices as p using (region_code, year)
    where i.year between (select year_from from reference.project_settings)
                     and (select year_to from reference.project_settings)
),

g as (
    select group_type, group_code, year, avg_sale_price_eur as price, transactions_count as n
    from marts.fct_group_affordability
),

recombined as (
    select
        nl.year,
        nl.n                                                        as n_nl,
        g4.n + rest.n                                               as n_two_way,
        g4.n + rr.n + rest3.n                                       as n_three_way,
        (g4.price * g4.n + rest.price * rest.n) / (g4.n + rest.n)   as price_two_way,
        nl.price                                                    as price_nl
    from g as nl
    join g as g4    on g4.year = nl.year    and g4.group_type = 'region_group'   and g4.group_code = 'G4'
    join g as rest  on rest.year = nl.year  and rest.group_type = 'region_group' and rest.group_code = 'REST_NL'
    join g as rr    on rr.year = nl.year    and rr.group_type = 'region_group_3' and rr.group_code = 'REST_RANDSTAD'
    join g as rest3 on rest3.year = nl.year and rest3.group_type = 'region_group_3' and rest3.group_code = 'REST_NL'
    where nl.group_type = 'nl'
),

issues as (
    select 'row count <> 18 x n_years' as issue, n_rows::varchar as detail from grain
    where n_rows <> 18 * (select year_to - year_from + 1 from reference.project_settings)
    union all
    select 'duplicate keys', (n_rows - n_keys)::varchar from grain where n_rows <> n_keys
    union all
    select 'missing price or income', group_type || ' ' || group_code || ' ' || year
    from marts.fct_group_affordability
    where avg_sale_price_eur is null or median_disposable_income_eur is null
    union all
    select '85792NED vs 83625NED price differs (NL/PV exact, G4 < 0.1 %)', region_code || ' ' || year
    from consistency
    where (region_code like 'GM%' and diff_pct >= 0.1)
       or (region_code not like 'GM%' and diff_pct > 0)
    union all
    select 'non-positive transaction count', group_type || ' ' || group_code || ' ' || year
    from marts.fct_group_affordability
    where transactions_count is null or transactions_count <= 0
    union all
    select 'transactions do not add up to NL', year::varchar
    from recombined
    where n_two_way <> n_nl or n_three_way <> n_nl
    union all
    select 'G4 + Rest of NL price does not recombine to NL', year::varchar
    from recombined
    where abs(price_two_way - price_nl) > 0.01
)

select * from issues
