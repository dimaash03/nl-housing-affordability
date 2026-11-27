-- Region groups follow the agreed rules (D-010, D-016). Returns one row per violation.
--
-- The agreed lists are written here as literals ON PURPOSE. The models read them from
-- config/cbs_tables.yaml (reference.project_settings); this test is the independent contract, so a
-- typo in the config cannot silently re-define the groups and still pass.
--
--   - config: G4 = GM0344, GM0363, GM0518, GM0599; Randstad provinces = PV26, PV27, PV28
--   - dim_province.is_randstad_province = exactly those three provinces
--   - dim_municipality: region_group_3 recomputed from the rule (G4 -> 'G4'; other municipality in
--     PV26/PV27/PV28 -> 'Rest of Randstad provinces'; everything else -> 'Rest of NL') matches the
--     stored value; region_group, is_g4 and the sort keys agree with it
--   - each G4 city sits in its expected province (a CBS province re-coding would show up here)
--   - Almere (GM0034, Flevoland) is in Rest of NL (documented D-010 limitation)
--   - group sizes in the 2026 division: 4 / 116 / 222 municipalities
--   - fct_group_affordability: the method labels say which aggregates are approximations
--     (income of G4 / Rest groups = household-weighted mean of municipal medians), and the household
--     counts of the two-way and three-way splits add up to the municipal total of the same year

with

settings as (
    select
        array_to_string(list_sort(g4_codes), ',')                as g4_codes,
        array_to_string(list_sort(randstad_province_codes), ',') as randstad_province_codes
    from reference.project_settings
),

expected_group as (
    select
        municipality_code,
        case
            when municipality_code in ('GM0344', 'GM0363', 'GM0518', 'GM0599')  then 'G4'
            when province_code in ('PV26', 'PV27', 'PV28')                     then 'Rest of Randstad provinces'
            else 'Rest of NL'
        end as expected_group_3
    from marts.dim_municipality
),

g4_province as (
    select * from (values
        ('GM0363', 'PV27'),   -- Amsterdam, Noord-Holland
        ('GM0599', 'PV28'),   -- Rotterdam, Zuid-Holland
        ('GM0518', 'PV28'),   -- 's-Gravenhage, Zuid-Holland
        ('GM0344', 'PV26')    -- Utrecht, Utrecht
    ) as t(municipality_code, province_code)
),

group_sizes as (
    select region_group_3, count(*) as n
    from marts.dim_municipality
    group by region_group_3
),

expected_sizes as (
    select * from (values ('G4', 4), ('Rest of Randstad provinces', 116), ('Rest of NL', 222))
        as t(region_group_3, n)
),

group_households as (
    select
        year,
        sum(households_count) filter (where group_type = 'region_group')    as households_two_way,
        sum(households_count) filter (where group_type = 'region_group_3')  as households_three_way
    from marts.fct_group_affordability
    group by year
),

municipal_households as (
    select year, sum(households_count) as households_municipal
    from marts.fct_affordability
    where not income_missing
    group by year
),

issues as (
    select 'config randstad_g4 is not the D-010 list' as issue, g4_codes as detail
    from settings where g4_codes <> 'GM0344,GM0363,GM0518,GM0599'
    union all
    select 'config randstad_provinces is not the D-010 list', randstad_province_codes
    from settings where randstad_province_codes <> 'PV26,PV27,PV28'
    union all
    select 'dim_province.is_randstad_province is not exactly PV26, PV27, PV28',
           string_agg(province_code, ',' order by province_code)
    from marts.dim_province
    where is_randstad_province
    having string_agg(province_code, ',' order by province_code) <> 'PV26,PV27,PV28'
    union all
    select 'region_group_3 does not follow the D-010 rule',
           d.municipality_code || ': ' || d.region_group_3 || ' <> ' || e.expected_group_3
    from marts.dim_municipality as d
    join expected_group as e using (municipality_code)
    where d.region_group_3 <> e.expected_group_3
    union all
    select 'region_group / is_g4 / sort keys disagree with region_group_3', municipality_code
    from marts.dim_municipality
    where region_group <> case when region_group_3 = 'G4' then 'G4' else 'Rest of NL' end
       or is_g4 <> (region_group_3 = 'G4')
       or region_group_3_sort <> case region_group_3 when 'G4' then 1
                                                     when 'Rest of Randstad provinces' then 2 else 3 end
       or (g4_sort_order is null) = is_g4
    union all
    select 'G4 city not in its expected province', g.municipality_code || ' in ' || coalesce(d.province_code, 'none')
    from g4_province as g
    left join marts.dim_municipality as d using (municipality_code)
    where d.province_code is distinct from g.province_code
    union all
    select 'Almere (GM0034) is not in Rest of NL / Flevoland', coalesce(region_group_3 || ' ' || province_code, 'missing')
    from (select 1) as one
    left join marts.dim_municipality on municipality_code = 'GM0034'
    where region_group_3 is distinct from 'Rest of NL' or province_code is distinct from 'PV24'
    union all
    select 'group size differs from 4 / 116 / 222',
           coalesce(e.region_group_3, s.region_group_3) || ': ' || coalesce(s.n, 0) || ' <> ' || coalesce(e.n, 0)
    from expected_sizes as e
    full join group_sizes as s using (region_group_3)
    where s.n is distinct from e.n
    union all
    select 'group method label is wrong', group_type || ' ' || group_code || ' ' || year
    from marts.fct_group_affordability
    where (group_type in ('nl', 'province')
           and (price_method <> 'cbs_published' or income_method <> 'cbs_published'))
       or (group_type in ('region_group', 'region_group_3')
           and (income_method <> 'household_weighted_median'
                or price_method <> case group_code when 'G4' then 'transaction_weighted' else 'exact_residual' end))
       or is_income_approximated <> (income_method = 'household_weighted_median')
    union all
    select 'group households do not add up to the municipal total', m.year::varchar
    from municipal_households as m
    left join group_households as g using (year)
    where g.households_two_way is distinct from m.households_municipal
       or g.households_three_way is distinct from m.households_municipal
)

select * from issues
