-- Only the income table carries a period status in staging (is_preliminary, D-008). For the other
-- tables every yearly period used in staging must be final ('Definitief'). If CBS publishes a
-- preliminary year there, this test fails: add period_status / is_preliminary to that staging
-- model (as in stg_cbs__household_income) instead of silently treating the year as final (QA P-5).
with periods as (
    select '83625NED' as table_id, trim(Key) as period_code, Status as period_status
    from raw.cbs_83625ned__dim_perioden
    union all
    select '70072ned', trim(Key), Status from raw.cbs_70072ned__dim_perioden
    union all
    select '85792NED', trim(Key), Status from raw.cbs_85792ned__dim_perioden
    union all
    select '86141NED', trim(Key), Status from raw.cbs_86141ned__dim_perioden
),

yearly as (
    select table_id, cast(left(period_code, 4) as integer) as year, period_status
    from periods
    where substr(period_code, 5, 2) = 'JJ'
)

select table_id, year, period_status
from yearly
where year >= 2011
  and (period_status is null or period_status <> 'Definitief')
order by table_id, year
