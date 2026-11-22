-- The 1 January 2026 division has 342 municipalities (D-006), all with a GM code and 12 provinces.
with summary as (
    select
        count(*)                                                 as n_municipalities,
        count(*) filter (where municipality_code not like 'GM%') as n_non_gm_codes,
        count(distinct province_code)                            as n_provinces
    from staging.stg_cbs__municipalities_2026
)

select * from summary
where n_municipalities <> 342 or n_non_gm_codes <> 0 or n_provinces <> 12
