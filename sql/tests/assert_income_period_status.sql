-- is_preliminary is derived from the CBS period status (D-008). Fail on any status value we do not
-- know how to interpret, and if a preliminary year is followed by a final one (statuses out of order).
with statuses as (
    select distinct year, period_status, is_preliminary
    from staging.stg_cbs__household_income
),

unknown_status as (
    select 'unknown period status' as issue, year, period_status
    from statuses
    where period_status is null
       or period_status not in ('Definitief', 'Voorlopig', 'Nader voorlopig')
),

final_after_preliminary as (
    select 'final year after a preliminary year' as issue, f.year, f.period_status
    from statuses as f
    join statuses as p
        on p.is_preliminary and not f.is_preliminary and f.year > p.year
)

select * from unknown_status
union all
select * from final_after_preliminary
