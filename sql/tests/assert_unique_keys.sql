-- Every staging model must be unique on its declared grain.
-- Returns one row per duplicated key (model, key, number of rows).
with duplicates as (
    select 'stg_cbs__house_prices' as model, region_code || '|' || year as key_value, count(*) as n
    from staging.stg_cbs__house_prices group by all having count(*) > 1
    union all
    select 'stg_cbs__household_income', region_code || '|' || year || '|' || household_group, count(*)
    from staging.stg_cbs__household_income group by all having count(*) > 1
    union all
    select 'stg_cbs__regional_key_figures', region_code || '|' || year, count(*)
    from staging.stg_cbs__regional_key_figures group by all having count(*) > 1
    union all
    select 'stg_cbs__cpi', cast(year as varchar), count(*)
    from staging.stg_cbs__cpi group by all having count(*) > 1
    union all
    select 'stg_cbs__municipalities_2026', municipality_code, count(*)
    from staging.stg_cbs__municipalities_2026 group by all having count(*) > 1
    union all
    select 'stg_cbs__house_price_index', region_code || '|' || year, count(*)
    from staging.stg_cbs__house_price_index group by all having count(*) > 1
    union all
    select 'stg_cbs__regions_history', region_code, count(*)
    from staging.stg_cbs__regions_history group by all having count(*) > 1
)

select * from duplicates
