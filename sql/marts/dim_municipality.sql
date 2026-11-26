-- dim_municipality
-- Source:  staging.stg_cbs__municipalities_2026 (86247NED, the 342 municipalities of 1 January 2026)
-- Grain:   one row per municipality_code (2026 division) -> 342 rows. Joins to fct_affordability on
--          municipality_code (many-to-one) and to dim_province on province_code.
-- Filters: none.
-- Decisions:
--   D-010  region_group (G4 vs Rest of NL, primary) and region_group_3 (secondary: G4 /
--          Rest of Randstad provinces = other municipalities in PV26, PV27, PV28 / Rest of NL).
--          Flevoland (Almere) stays in Rest of NL (limitation). urbanity_class is the
--          "Randstad effect vs big-city effect" lens.
--   D-028  province name/code are kept here as well as in dim_province (denormalised), so Power BI
--          needs one relationship for municipality slicers; dim_province serves province-level facts.

with

municipalities as (
    select * from staging.stg_cbs__municipalities_2026
),

-- The four G4 cities (D-010). Listed once; every group column derives from this CTE.
g4 as (
    select * from (values
        ('GM0363', 1),   -- Amsterdam
        ('GM0599', 2),   -- Rotterdam
        ('GM0518', 3),   -- 's-Gravenhage (Den Haag)
        ('GM0344', 4)    -- Utrecht
    ) as t(municipality_code, g4_sort_order)
),

randstad_provinces as (
    select * from (values ('PV26'), ('PV27'), ('PV28')) as t(province_code)
),

-- CBS labels are Dutch; English labels for the dashboard. Codes 1-5 from 86247NED Code_54.
urbanity_labels as (
    select * from (values
        (1, 'Very strongly urban'),
        (2, 'Strongly urban'),
        (3, 'Moderately urban'),
        (4, 'Hardly urban'),
        (5, 'Not urban')
    ) as t(urbanity_class, urbanity_class_label_en)
)

select
    m.municipality_code,
    m.municipality_name,
    m.province_code,
    m.province_name,
    m.corop_code,
    m.corop_name,
    g.municipality_code is not null                                   as is_g4,
    case when g.municipality_code is not null then 'G4' else 'Rest of NL' end
                                                                      as region_group,
    case
        when g.municipality_code is not null  then 'G4'
        when rp.province_code is not null     then 'Rest of Randstad provinces'
        else 'Rest of NL'
    end                                                               as region_group_3,
    -- explicit sort keys so Power BI does not order the groups alphabetically
    case
        when g.municipality_code is not null  then 1
        when rp.province_code is not null     then 2
        else 3
    end                                                               as region_group_3_sort,
    g.g4_sort_order,
    m.urbanity_class,
    m.urbanity_class_label                                            as urbanity_class_label_nl,
    u.urbanity_class_label_en,
    m.size_class_code,
    m.size_class                                                      as size_class_label_nl,
    m.population                                                      as population_2026
from municipalities as m
left join g4 as g
    on g.municipality_code = m.municipality_code
left join randstad_provinces as rp
    on rp.province_code = m.province_code
left join urbanity_labels as u
    on u.urbanity_class = m.urbanity_class
order by m.municipality_code
