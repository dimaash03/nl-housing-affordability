-- The dimensions are faithful to CBS. Returns one row per violation.
--
--   1. dim_municipality (code, name, province, COROP) = raw 86247NED, trimmed, in both directions.
--      Compared with RAW, not staging, so a renaming/trimming bug in staging is caught as well.
--   2. dim_province (code, name) = the distinct province pairs of raw 86247NED.
--   3. The 12 province codes are exactly the PV codes of every other source that has provinces
--      (83625NED, 86380NED, 85792NED, 70072ned), and the labels agree once the StatLine " (PV)"
--      suffix is removed. A group join on a province code can therefore never drop a province.
--   4. The 342 municipality codes are exactly the GM codes of 86380NED (also in the 2026 division),
--      and the names agree. StatLine labels add " (gemeente)" where a name is also a province
--      (Groningen, Utrecht, 's-Gravenhage) and write the province suffix differently
--      ("Hengelo (O.)" vs 86247NED "Hengelo (OV)", 8 municipalities in the 2026 division). So the
--      names must be equal after removing " (gemeente)", or differ only inside a trailing
--      "(...)" suffix that both labels have. dim_municipality keeps the 86247NED spelling.
--   5. The G4 codes exist in 85792NED (source of the G4 transaction-weighted price).

with

source_municipalities as (
    select
        trim(Code_1)   as municipality_code,
        trim(Naam_2)   as municipality_name,
        trim(Code_28)  as province_code,
        trim(Naam_29)  as province_name,
        trim(Code_10)  as corop_code,
        trim(Naam_11)  as corop_name
    from raw.cbs_86247ned
),

dim_municipalities as (
    select municipality_code, municipality_name, province_code, province_name, corop_code, corop_name
    from marts.dim_municipality
),

source_provinces as (
    select distinct province_code, province_name from source_municipalities
),

other_provinces as (
    select '83625NED' as table_id, trim(Key) as province_code, regexp_replace(Title, ' \(PV\)$', '') as label
    from raw.cbs_83625ned__dim_regios where trim(Key) like 'PV%'
    union all
    select '86380NED', trim(Key), regexp_replace(Title, ' \(PV\)$', '')
    from raw.cbs_86380ned__dim_regios where trim(Key) like 'PV%'
    union all
    select '85792NED', trim(Key), regexp_replace(Title, ' \(PV\)$', '')
    from raw.cbs_85792ned__dim_regios where trim(Key) like 'PV%'
    union all
    select '70072ned', trim(Key), regexp_replace(Title, ' \(PV\)$', '')
    from raw.cbs_70072ned__dim_regios where trim(Key) like 'PV%'
),

source_tables as (
    select * from (values ('83625NED'), ('86380NED'), ('85792NED'), ('70072ned')) as t(table_id)
),

income_municipalities as (
    select trim(Key) as municipality_code, regexp_replace(Title, ' \(gemeente\)$', '') as label
    from raw.cbs_86380ned__dim_regios
    where trim(Key) like 'GM%'
),

name_pairs as (
    select
        coalesce(d.municipality_code, i.municipality_code)  as municipality_code,
        d.municipality_name,
        i.label
    from marts.dim_municipality as d
    full join income_municipalities as i using (municipality_code)
),

issues as (
    select 'dim_municipality row not in 86247NED' as issue, municipality_code || ' ' || municipality_name as detail
    from (select * from dim_municipalities except select * from source_municipalities)
    union all
    select '86247NED row not in dim_municipality', municipality_code || ' ' || municipality_name
    from (select * from source_municipalities except select * from dim_municipalities)
    union all
    select 'dim_province differs from 86247NED', coalesce(d.province_code, s.province_code)
    from (select province_code, province_name from marts.dim_province) as d
    full join source_provinces as s using (province_code, province_name)
    where d.province_code is null or s.province_code is null
    union all
    select 'province code missing in ' || t.table_id, p.province_code
    from marts.dim_province as p
    cross join source_tables as t
    anti join other_provinces as o on o.table_id = t.table_id and o.province_code = p.province_code
    union all
    select 'extra province code in ' || o.table_id, o.province_code
    from other_provinces as o
    anti join marts.dim_province as p using (province_code)
    union all
    select 'province label differs in ' || o.table_id, o.province_code || ': ' || o.label || ' <> ' || p.province_name
    from other_provinces as o
    join marts.dim_province as p using (province_code)
    where o.label <> p.province_name
    union all
    select 'municipality code only in one of dim_municipality / 86380NED', municipality_code
    from name_pairs
    where municipality_name is null or label is null
    union all
    select 'municipality name differs from 86380NED', municipality_code || ': ' || municipality_name || ' <> ' || label
    from name_pairs
    where municipality_name <> label
      and not (
          regexp_matches(municipality_name, ' \([^)]+\)$')
          and regexp_matches(label, ' \([^)]+\)$')
          and regexp_replace(municipality_name, ' \([^)]+\)$', '') = regexp_replace(label, ' \([^)]+\)$', '')
      )
    union all
    select 'G4 code missing in 85792NED', d.municipality_code
    from marts.dim_municipality as d
    anti join (select trim(Key) as municipality_code from raw.cbs_85792ned__dim_regios) as r using (municipality_code)
    where d.is_g4
)

select * from issues
