-- Star schema integrity for the marts layer. Returns one row per violation.
--   - fct_affordability: exactly 342 municipalities x n_years (15 for 2011-2025, reference.project_settings),
--     unique on (municipality_code, year)
--   - each dimension unique on its key, with the expected row count
--   - every fact key exists in its dimension (no orphan rows in Power BI relationships)
--   - G4 = exactly the four cities of D-010; every municipality has a region group
with

n_years as (
    select year_to - year_from + 1 as n from reference.project_settings
),

fct_counts as (
    select
        count(*)                                               as n_rows,
        count(distinct municipality_code || '|' || year)       as n_keys
    from marts.fct_affordability
),

issues as (
    select 'fct_affordability row count <> 342 x n_years' as issue, n_rows::varchar as detail
    from fct_counts where n_rows <> 342 * (select n from n_years)
    union all
    select 'fct_affordability duplicate keys', (n_rows - n_keys)::varchar
    from fct_counts where n_rows <> n_keys
    union all
    select 'dim_municipality rows <> 342 or not unique', count(*)::varchar
    from marts.dim_municipality
    having count(*) <> 342 or count(distinct municipality_code) <> 342
    union all
    select 'dim_province rows <> 12 or not unique', count(*)::varchar
    from marts.dim_province
    having count(*) <> 12 or count(distinct province_code) <> 12
    union all
    select 'dim_year rows <> n_years or not unique', count(*)::varchar
    from marts.dim_year
    having count(*) <> (select n from n_years) or count(distinct year) <> (select n from n_years)
    union all
    select 'fct municipality_code missing in dim_municipality', f.municipality_code
    from marts.fct_affordability as f
    anti join marts.dim_municipality as d using (municipality_code)
    union all
    select 'fct year missing in dim_year', f.year::varchar
    from marts.fct_affordability as f
    anti join marts.dim_year as d using (year)
    union all
    select 'dim_municipality province_code missing in dim_province', m.province_code
    from marts.dim_municipality as m
    anti join marts.dim_province as p using (province_code)
    union all
    select 'G4 is not exactly GM0344, GM0363, GM0518, GM0599', string_agg(municipality_code, ',' order by municipality_code)
    from marts.dim_municipality
    where is_g4
    having string_agg(municipality_code, ',' order by municipality_code) <> 'GM0344,GM0363,GM0518,GM0599'
    union all
    select 'dim_municipality without region_group / region_group_3 / urbanity label', municipality_code
    from marts.dim_municipality
    where region_group is null or region_group_3 is null or urbanity_class_label_en is null
)

select * from issues
