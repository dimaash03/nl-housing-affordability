-- The committed herindeling mapping (data/reference/municipality_mapping_2026.csv, loaded by `make load`
-- into reference.municipality_mapping_2026) must fit the staging data it is joined to (QA H-5).
-- A stale CSV (e.g. after a new herindeling or a CBS revision) would otherwise drop codes silently
-- in the marts. Fix: `make harmonise`, review and commit the CSV diff.
-- Checks:
--   1. every GM code with a price in staging has a mapping row (GM0998/GM0999 pseudo codes excluded, D-023);
--   2. every target code is one of the 342 municipalities of 2026;
--   3. every 2026 municipality receives at least one historical code;
--   4. the weights of every old code sum to 1 (stored with 6 decimals).
with mapping as (
    select * from reference.municipality_mapping_2026
),

priced_codes as (
    select distinct region_code
    from staging.stg_cbs__house_prices
    where region_type = 'GM'
      and region_code not in ('GM0998', 'GM0999')
),

unmapped_price_code as (
    select 'priced code not in mapping' as issue, p.region_code as code
    from priced_codes as p
    anti join mapping as m on m.old_code = p.region_code
),

unknown_target as (
    select distinct 'target not in the 2026 list' as issue, m.new_code_2026 as code
    from mapping as m
    anti join staging.stg_cbs__municipalities_2026 as g on g.municipality_code = m.new_code_2026
),

uncovered_municipality as (
    select '2026 municipality without a mapping row' as issue, g.municipality_code as code
    from staging.stg_cbs__municipalities_2026 as g
    anti join mapping as m on m.new_code_2026 = g.municipality_code
),

bad_weight_sum as (
    select 'weights do not sum to 1' as issue, old_code as code
    from mapping
    group by old_code
    having abs(sum(weight) - 1) > 1e-6
)

select * from unmapped_price_code
union all
select * from unknown_target
union all
select * from uncovered_municipality
union all
select * from bad_weight_sum
order by issue, code
