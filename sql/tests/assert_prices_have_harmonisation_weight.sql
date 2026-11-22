-- D-007 weights harmonised prices by owner-occupied stock from 70072ned (same year, same historical code).
-- Every municipality-year with a price must therefore have owner_occupied_stock (D-011 check).
--
-- Known exception (DATA_DICTIONARY section 4, item 7): in 2015 83625NED has prices for both
-- GM1921 De Friese Meren and GM1940 De Fryske Marren (renamed with a new code on 1 July 2015),
-- while 70072ned has only GM1921 for 2015. Both map to GM1940, so the weight gap is handled by the
-- harmonisation. Any OTHER gap fails this test.
with known_exceptions as (
    select * from (values ('GM1940', 2015)) as t(region_code, year)
),

missing_weight as (
    select p.region_code, p.year
    from staging.stg_cbs__house_prices as p
    left join staging.stg_cbs__regional_key_figures as k
        on p.region_code = k.region_code
       and p.year = k.year
    where p.region_type = 'GM'
      and k.owner_occupied_stock is null
)

select * from missing_weight
except
select * from known_exceptions
