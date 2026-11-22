-- 85792NED covers 21 regions (NL01, 4 LD, 12 PV, the G4) in every year (D-015),
-- and the G4 must be the four municipalities of D-010.
with per_year as (
    select
        year,
        count(*)                                                    as n_regions,
        count(*) filter (where region_type = 'GM')                  as n_gm,
        count(*) filter (where region_code in ('GM0363', 'GM0599', 'GM0518', 'GM0344')) as n_g4
    from staging.stg_cbs__house_price_index
    group by year
)

select * from per_year
where n_regions <> 21 or n_gm <> 4 or n_g4 <> 4
