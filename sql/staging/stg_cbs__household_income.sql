-- stg_cbs__household_income
-- Source:  CBS 86380NED "Inkomen van huishoudens; huishoudenskenmerken, regio (indeling 2026)"
--          (raw.cbs_86380ned, period status from raw.cbs_86380ned__dim_perioden)
-- Grain:   one row per region_code x year x household_group
-- Filters: Populatie = '3000870' (private households excl. student households, D-003);
--          KenmerkenVanHuishoudens in ('1050010' all private households, '1014800' owner-occupiers);
--          yearly periods only
-- Notes:
--   - All regions are kept (NL, LD, PV, CR, AM, GM): province and NL rows are needed for D-016.
--   - GM codes are already in the 1 January 2026 division for every year (no harmonisation needed).
--   - Units: CBS publishes households in x 1 000 and income in 1 000 euro, both with 1 decimal,
--     so after conversion households are exact to 100 and incomes to 100 euro.
--   - NULL incomes are kept (suppressed by CBS, e.g. very small municipalities); flagged in marts.
--   - is_preliminary comes from the CBS period status (D-008), never from a hard-coded year.

with source as (
    select * from raw.cbs_86380ned
),

period_status as (
    select
        trim(Key)                                   as period_code,
        trim(Status)                                as period_status
    from raw.cbs_86380ned__dim_perioden
),

renamed as (
    select
        trim(Populatie)                             as population_code,
        trim(KenmerkenVanHuishoudens)               as household_characteristic_code,
        trim(RegioS)                                as region_code,
        trim(Perioden)                              as period_code,
        ParticuliereHuishoudens_1                   as households_thousands,
        GemiddeldBesteedbaarInkomen_5               as mean_disposable_income_eur_k,
        MediaanBesteedbaarInkomen_6                 as median_disposable_income_eur_k,
        GemiddeldGestandaardiseerdInkomen_3         as mean_standardised_income_eur_k,
        MediaanGestandaardiseerdInkomen_4           as median_standardised_income_eur_k
    from source
),

filtered as (
    select *
    from renamed
    where population_code = '3000870'
      and household_characteristic_code in ('1050010', '1014800')
      and substr(period_code, 5, 2) = 'JJ'
)

select
    f.region_code,
    left(f.region_code, 2)                          as region_type,   -- GM / PV / LD / NL / CR / AM
    cast(left(f.period_code, 4) as integer)         as year,
    case f.household_characteristic_code
        when '1050010' then 'all'
        when '1014800' then 'owner_occupier'
    end                                             as household_group,
    -- round() removes float noise from the unit conversion (e.g. 4.9 * 1000 = 4900.000000000001)
    cast(round(f.households_thousands * 1000) as bigint) as households_count,
    round(f.mean_disposable_income_eur_k * 1000)     as mean_disposable_income_eur,
    round(f.median_disposable_income_eur_k * 1000)   as median_disposable_income_eur,
    round(f.mean_standardised_income_eur_k * 1000)   as mean_standardised_income_eur,
    round(f.median_standardised_income_eur_k * 1000) as median_standardised_income_eur,
    p.period_status,
    -- 'Nader voorlopig' (revised provisional) is also not final
    p.period_status in ('Voorlopig', 'Nader voorlopig') as is_preliminary
from filtered as f
left join period_status as p
    on f.period_code = p.period_code
