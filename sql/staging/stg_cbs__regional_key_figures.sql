-- stg_cbs__regional_key_figures
-- Source:  CBS 70072ned "Regionale kerncijfers Nederland" (raw.cbs_70072ned)
-- Grain:   one row per region_code x year
-- Filters: yearly periods, year >= 2011; rows where all selected measures are NULL are dropped
-- Notes:
--   - Regions are in the boundaries of the reporting year (historical GM codes, harmonised later, D-007/D-011).
--   - Like 83625NED, CBS lists all 728 GM codes for every year; all-NULL rows are municipalities that
--     did not exist in that year and are dropped.
--   - The latest year (2026) has only population and WOZ; households, stock and share are NULL there.
--   - owner_occupied_stock = dwelling_stock * owner_occupied_share_pct / 100 is the harmonisation weight
--     for average prices (D-007). It is an estimate, so it is not rounded. Precision of the share
--     (Koopwoningen_64): one decimal in 2011-2020, but whole percentages only from 2021 onwards
--     (0 non-integer GM values per year in 2021-2025, QA P-2). The weight for 2021-2022 is therefore
--     coarser (+/- 0.5 pp of the stock); see DATA_DICTIONARY 2.3.
--   - Units: WOZ is published in 1 000 euro (0 decimals) -> mean_woz_value_eur exact to 1 000 euro.

with source as (
    select * from raw.cbs_70072ned
),

renamed as (
    select
        trim(RegioS)                         as region_code,
        trim(Perioden)                       as period_code,
        TotaleBevolking_1                    as population,
        TotaalParticuliereHuishoudens_51     as households_count,
        GemiddeldeHuishoudensgrootte_58      as avg_household_size,
        Woningvoorraad_59                    as dwelling_stock,
        Koopwoningen_64                      as owner_occupied_share_pct,
        GemiddeldeWOZWaardeVanWoningen_63    as mean_woz_value_eur_k
    from source
),

yearly as (
    select
        region_code,
        left(region_code, 2)                  as region_type,   -- GM / PV / LD / CR / NL
        cast(left(period_code, 4) as integer) as year,
        cast(population as bigint)            as population,
        cast(households_count as bigint)      as households_count,
        avg_household_size,
        cast(dwelling_stock as bigint)        as dwelling_stock,
        owner_occupied_share_pct,
        mean_woz_value_eur_k * 1000           as mean_woz_value_eur
    from renamed
    where substr(period_code, 5, 2) = 'JJ'
)

select
    region_code,
    region_type,
    year,
    population,
    households_count,
    avg_household_size,
    dwelling_stock,
    owner_occupied_share_pct,
    dwelling_stock * owner_occupied_share_pct / 100 as owner_occupied_stock,
    mean_woz_value_eur
from yearly
where year >= 2011
  and coalesce(population, households_count, avg_household_size, dwelling_stock,
               owner_occupied_share_pct, mean_woz_value_eur) is not null
