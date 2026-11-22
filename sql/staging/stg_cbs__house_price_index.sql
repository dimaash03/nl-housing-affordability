-- stg_cbs__house_price_index
-- Source:  CBS 85792NED "Bestaande koopwoningen; verkoopprijzen, prijsindex 2020=100, regio"
--          (raw.cbs_85792ned)
-- Grain:   one row per region_code x year
-- Filters: yearly periods only (YYYYJJ00); quarterly and monthly rows dropped. All years kept.
-- Notes:
--   - Only 21 regions: NL01, LD01-LD04, the 12 provinces and the G4 municipalities (D-015).
--   - price_index_2020 is quality-adjusted (2020 = 100); avg_sale_price_eur is the
--     plain mean and equals 83625NED for NL and the G4. transactions_count feeds D-016 (G4 / Rest of NL).

with source as (
    select * from raw.cbs_85792ned
),

renamed as (
    select
        trim(RegioS)                     as region_code,
        trim(Perioden)                   as period_code,
        PrijsindexVerkoopprijzen_1       as price_index_2020,
        VerkochteWoningen_4              as transactions_count,
        GemiddeldeVerkoopprijs_7         as avg_sale_price_eur
    from source
)

select
    region_code,
    left(region_code, 2)                  as region_type,   -- GM / PV / LD / NL
    cast(left(period_code, 4) as integer) as year,
    price_index_2020,
    cast(transactions_count as bigint)    as transactions_count,
    avg_sale_price_eur
from renamed
where substr(period_code, 5, 2) = 'JJ'
