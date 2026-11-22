-- Prices, incomes, counts and stock must be positive where present; shares within 0-100 %.
with violations as (
    select 'stg_cbs__house_prices' as model, region_code, year, 'avg_sale_price_eur <= 0' as rule
    from staging.stg_cbs__house_prices where avg_sale_price_eur <= 0
    union all
    select 'stg_cbs__household_income', region_code, year, 'income or households <= 0'
    from staging.stg_cbs__household_income
    where median_disposable_income_eur <= 0 or mean_disposable_income_eur <= 0
       or median_standardised_income_eur <= 0 or mean_standardised_income_eur <= 0
       or households_count <= 0
    union all
    select 'stg_cbs__regional_key_figures', region_code, year, 'count/value <= 0 or share outside 0-100'
    from staging.stg_cbs__regional_key_figures
    where population <= 0 or households_count <= 0 or avg_household_size <= 0 or dwelling_stock <= 0
       or mean_woz_value_eur <= 0
       or owner_occupied_share_pct < 0 or owner_occupied_share_pct > 100
    union all
    select 'stg_cbs__house_price_index', region_code, year, 'index/count/price <= 0'
    from staging.stg_cbs__house_price_index
    where price_index_2020 <= 0 or transactions_count <= 0 or avg_sale_price_eur <= 0
    union all
    select 'stg_cbs__cpi', 'NL01', year, 'cpi <= 0'
    from staging.stg_cbs__cpi where cpi_2025_index <= 0
)

select * from violations
