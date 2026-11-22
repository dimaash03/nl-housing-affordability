-- stg_cbs__house_prices
-- Source:  CBS 83625NED "Bestaande koopwoningen; gemiddelde verkoopprijzen, regio" (raw.cbs_83625ned)
-- Grain:   one row per region_code x year
-- Filters: yearly periods only (YYYYJJ00), year >= 2011 (first income year, D-008),
--          rows with a NULL price dropped (see note)
-- Notes:
--   - Regions are in the boundaries of the reporting year (historical GM codes, harmonised later).
--   - CBS returns every GM code ever used (728) for every year; a NULL price almost always means
--     "municipality did not exist in that year". Those rows carry no information and are dropped here;
--     coverage against the 2026 municipality list is checked downstream.
--   - Price is the mean of transacted homes (not quality-adjusted), already in euro.

with source as (
    select * from raw.cbs_83625ned
),

renamed as (
    select
        trim(RegioS)                         as region_code,
        trim(Perioden)                       as period_code,
        GemiddeldeVerkoopprijs_1             as avg_sale_price_eur
    from source
),

yearly as (
    select
        region_code,
        left(region_code, 2)                 as region_type,   -- GM / PV / LD / NL
        cast(left(period_code, 4) as integer) as year,
        avg_sale_price_eur
    from renamed
    where substr(period_code, 5, 2) = 'JJ'
)

select
    region_code,
    region_type,
    year,
    avg_sale_price_eur
from yearly
where year >= 2011
  and avg_sale_price_eur is not null
