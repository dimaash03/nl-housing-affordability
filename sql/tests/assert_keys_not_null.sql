-- Grain columns must never be NULL (a NULL key would silently drop rows in joins).
with null_keys as (
    select 'stg_cbs__house_prices' as model, count(*) as n
    from staging.stg_cbs__house_prices where region_code is null or year is null or region_type is null
    union all
    select 'stg_cbs__household_income', count(*)
    from staging.stg_cbs__household_income
    where region_code is null or year is null or household_group is null or is_preliminary is null
    union all
    select 'stg_cbs__regional_key_figures', count(*)
    from staging.stg_cbs__regional_key_figures where region_code is null or year is null
    union all
    select 'stg_cbs__cpi', count(*) from staging.stg_cbs__cpi where year is null
    union all
    select 'stg_cbs__municipalities_2026', count(*)
    from staging.stg_cbs__municipalities_2026
    where municipality_code is null or province_code is null or urbanity_class is null
    union all
    select 'stg_cbs__house_price_index', count(*)
    from staging.stg_cbs__house_price_index where region_code is null or year is null
    union all
    select 'stg_cbs__regions_history', count(*)
    from staging.stg_cbs__regions_history where region_code is null or begin_date is null
)

select * from null_keys where n > 0
