-- Null rate of the primary income measure (median disposable income).
-- CBS suppresses income only for a handful of very small municipalities (2025: 3 of 342),
-- so per year and household group at most 1 % of GM rows may be NULL; NL and PV rows never.
with rates as (
    select
        year,
        household_group,
        region_type,
        count(*)                                                        as n_rows,
        count(*) filter (where median_disposable_income_eur is null)    as n_null,
        round(100.0 * count(*) filter (where median_disposable_income_eur is null) / count(*), 2) as null_pct
    from staging.stg_cbs__household_income
    where region_type in ('GM', 'PV', 'NL')
    group by all
)

select * from rates
where (region_type = 'GM' and null_pct > 1.0)
   or (region_type in ('PV', 'NL') and n_null > 0)
