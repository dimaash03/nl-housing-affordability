-- stg_cbs__municipalities_2026
-- Source:  CBS 86247NED "Gebieden in Nederland 2026" (raw.cbs_86247ned)
-- Grain:   one row per municipality (342 municipalities of the 1 January 2026 division)
-- Filters: none
-- Notes:
--   - All code and name columns are space-padded in the raw table and are trimmed here.
--   - urbanity_class: 1 = very strongly urban ... 5 = not urban (D-010, "big-city effect" lens).
--   - population = Inwonertal_56 as published in this table (CBS reference date, see table metadata).

with source as (
    select * from raw.cbs_86247ned
),

renamed as (
    select
        trim(Code_1)                     as municipality_code,
        trim(Naam_2)                     as municipality_name,
        trim(Code_28)                    as province_code,
        trim(Naam_29)                    as province_name,
        trim(Code_10)                    as corop_code,
        trim(Naam_11)                    as corop_name,
        trim(Code_26)                    as landsdeel_code,
        trim(Naam_27)                    as landsdeel_name,
        trim(Code_52)                    as size_class_code,
        trim(Omschrijving_53)            as size_class,
        trim(Code_54)                    as urbanity_class_code,
        trim(Omschrijving_55)            as urbanity_class_label,
        Inwonertal_56                    as population
    from source
)

select
    municipality_code,
    municipality_name,
    province_code,
    province_name,
    corop_code,
    corop_name,
    landsdeel_code,
    landsdeel_name,
    cast(size_class_code as integer)     as size_class_code,   -- 1 = < 5 000 inhabitants ... 8 = 250 000 or more
    size_class,
    cast(urbanity_class_code as integer) as urbanity_class,
    urbanity_class_label,
    cast(population as bigint)           as population
from renamed
