-- stg_cbs__regions_history
-- Source:  CBS 70739ned "Gebieden; overzicht vanaf 1830"
--          (raw.cbs_70739ned + raw.cbs_70739ned__dim_regios for the free-text description)
-- Grain:   one row per region_code (municipalities, provinces, COROP regions, landsdelen since 1830)
-- Filters: none
-- Notes:
--   - Dates come from the sortable YYYYMMDD fields (the display fields are Dutch text, '01 jan 1830').
--     strptime (not try_strptime) on purpose: an unexpected format fails the build instead of becoming NULL.
--     An empty end date means the region still exists -> NULL end_date.
--   - region_description is the RAW CBS text with the reorganisation history ("Opgeheven per ...,
--     overgegaan naar: ..."). It is deliberately NOT parsed here: the herindeling mapping is built and
--     tested in Python (D-007, src/nl_housing/harmonise.py).

with source as (
    select * from raw.cbs_70739ned
),

regions as (
    select
        trim(Key)                        as region_code,
        trim(Title)                      as region_name,
        Description                      as region_description
    from raw.cbs_70739ned__dim_regios
),

renamed as (
    select
        trim(RegioS)                                              as region_code,
        trim(GebiedsOfGemeentecode_3)                             as area_or_municipality_code,
        nullif(trim(Provincie_4), '')                             as province_name,
        strptime(nullif(trim(BegindatumSorteerveld_6), ''), '%Y%m%d')::date as begin_date,
        strptime(nullif(trim(EinddatumSorteerveld_7), ''), '%Y%m%d')::date  as end_date
    from source
)

select
    r.region_code,
    left(r.region_code, 2)               as region_type,   -- GM / PV / CR / LD
    g.region_name,
    r.area_or_municipality_code,
    r.province_name,
    r.begin_date,
    r.end_date,
    g.region_description
from renamed as r
left join regions as g
    on r.region_code = g.region_code
