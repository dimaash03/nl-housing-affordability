-- reference.project_settings (written by nl_housing.transform from config/cbs_tables.yaml `project:`)
-- is usable and consistent with the column names. Returns one row per violation.
--   - exactly one row; the window is ordered and the base year is its first year
--   - the growth columns are named *_since_2011_* (D-017). The models compute growth against
--     base_year from the config, so moving the window start without renaming those columns would
--     publish e.g. growth since 2013 under a "since 2011" name. This test is the reminder: change
--     the column names (and DATA_DICTIONARY / DAX) together with analysis_years[0].
--   - every configured year exists in the fact and in dim_year (no silent truncation)

with

settings as (
    select * from reference.project_settings
),

issues as (
    select 'project_settings must have exactly one row' as issue, count(*)::varchar as detail
    from settings
    having count(*) <> 1
    union all
    select 'analysis window is not ordered or base_year <> year_from',
           year_from || '-' || year_to || ', base ' || base_year
    from settings
    where year_from > year_to or base_year <> year_from
    union all
    select 'base_year <> 2011 but growth columns are named *_since_2011_* (rename them, D-017)',
           base_year::varchar
    from settings
    where base_year <> 2011
    union all
    select 'configured year missing in fct_affordability / dim_year', y.year::varchar
    from (select unnest(range(year_from, year_to + 1))::integer as year from settings) as y
    where y.year not in (select year from marts.fct_affordability)
       or y.year not in (select year from marts.dim_year)
)

select * from issues
