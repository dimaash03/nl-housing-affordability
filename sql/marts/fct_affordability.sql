-- fct_affordability
-- Source:  staging.stg_cbs__house_prices         (83625NED, average sale price, boundaries of the reporting year)
--          staging.stg_cbs__regional_key_figures  (70072ned, owner-occupied stock = price weight)
--          staging.stg_cbs__household_income      (86380NED, already in the 2026 division)
--          staging.stg_cbs__cpi                   (86141NED, yearly CPI 2025 = 100)
--          staging.stg_cbs__municipalities_2026   (86247NED, the 342 municipalities of 1 January 2026)
--          reference.municipality_mapping_2026     (historical GM code -> 2026 code; committed CSV,
--                                                   loaded by `make load`, PR #4)
-- Grain:   one row per municipality_code (2026 division) x year, 2011-2025 -> 342 x 15 = 5 130 rows.
-- Filters: GM rows only, pseudo-municipalities GM0998/GM0999 excluded (D-023, proposed);
--          analysis window 2011-2025 (D-008).
-- Decisions:
--   D-003  income = median disposable household income, private households excl. students;
--          owner-occupier income is the mandatory sensitivity (second PTI).
--   D-004  PTI = avg sale price / median disposable income (mean/median mix: compare changes and ranks).
--   D-007  harmonised price = owner-occupied-stock-weighted mean of the historical codes' averages.
--   D-022  (proposed, PR #4) mid-year rename GM1921/GM1940 2015 = one territorial unit.
--   D-008  base year for growth = 2011; is_preliminary comes from CBS Perioden.Status, never from the year.
--   D-009  no imputation; low_reliability (< 5 000 households) and income_missing rows are kept
--          but get no rank.
--   D-017  column names.
-- Not here on purpose: province / G4 / region_group columns (dim_municipality) and group-level PTI
-- (D-016: group PTI must be built from group price and group income, not from these ratios).

with

-- 1. Historical -> 2026 code mapping (456 rows; weights sum to 1 per old_code). Coverage of every
--    priced code is enforced by sql/tests/assert_mapping_covers_staging.sql, so the inner join in
--    prices_harmonised cannot silently drop an unmapped code.
mapping as (
    select
        old_code,
        new_code_2026,
        weight,
        change_type
    from reference.municipality_mapping_2026
),

-- 2. Every priced municipality-year in its own (historical) boundaries, with the owner-occupied
--    stock of the SAME code and year as the weight (both tables use reporting-year boundaries).
prices_raw as (
    select
        p.region_code                 as old_code,
        p.year,
        p.avg_sale_price_eur,
        k.owner_occupied_stock
    from staging.stg_cbs__house_prices as p
    left join staging.stg_cbs__regional_key_figures as k
        on  k.region_code = p.region_code
        and k.year = p.year
    where p.region_type = 'GM'
      and p.region_code not in ('GM0998', 'GM0999')   -- pseudo-municipalities (D-023)
      and p.year between 2011 and 2025
      and p.avg_sale_price_eur is not null
),

-- 3. Mid-year renames (harmonisation.md 5.2; only case: GM1921 -> GM1940 on 2015-07-01).
--    If a renamed code AND its successor both have a price in the same year, they describe the same
--    territory in two halves of the year. 70072ned (reference date 1 January) has a stock only for the
--    old code, so the pair is merged into one unit: simple mean of the two prices, and the stock that
--    exists. Same rule as the Python reference weight_sensitivity._territorial_units().
renames as (
    select old_code, new_code_2026 as successor_code
    from mapping
    where change_type = 'rename'
),

prices_old as (
    select
        coalesce(r.successor_code, pr.old_code)  as unit_code,
        pr.year,
        avg(pr.avg_sale_price_eur)               as avg_sale_price_eur,
        avg(pr.owner_occupied_stock)             as owner_occupied_stock,  -- avg ignores the missing one
        list(distinct pr.old_code)               as source_codes            -- kept for is_harmonised
    from prices_raw as pr
    left join renames as r
        on  r.old_code = pr.old_code
        -- only remap when the successor is priced in the same year (otherwise the code is a normal row)
        and exists (
            select 1 from prices_raw as s
            where s.old_code = r.successor_code and s.year = pr.year
        )
    group by all
),

-- 4. Harmonised price per 2026 municipality and year (D-007):
--      avg_sale_price_eur = sum(price * stock * weight) / sum(stock * weight)
--    `weight` is the mapping share (1 for merges/renames/identity, inhabitant share for 6 splits).
--    A priced unit without a stock would silently drop out of both sums, so it fails the build instead.
prices_harmonised as (
    select
        m.new_code_2026                                              as municipality_code,
        po.year,
        case
            -- guard inside the output expression, so the optimizer cannot prune it
            when bool_or(po.owner_occupied_stock is null)
            then error('fct_affordability: ' || m.new_code_2026 || ' ' || po.year
                       || ' has a priced source code without owner_occupied_stock (harmonisation weight)')
            else sum(po.avg_sale_price_eur * po.owner_occupied_stock * m.weight)
                 / sum(po.owner_occupied_stock * m.weight)
        end                                                          as avg_sale_price_eur,
        -- more than one historical code contributed in this year (incl. the 2015 rename pair).
        -- Units have disjoint source codes, so summing list lengths = count(distinct old_code)
        -- without multiplying rows (an unnest here would double-weight the rename pair).
        sum(len(po.source_codes)) > 1                                as is_harmonised
    from prices_old as po
    inner join mapping as m
        on m.old_code = po.unit_code
    group by m.new_code_2026, po.year
),

-- 5. Income: one row per municipality x year. 86380NED is already in the 2026 division,
--    so no harmonisation. households_count = ParticuliereHuishoudens_1 * 1000 (all households).
income as (
    select
        region_code                                                                  as municipality_code,
        year,
        max(case when household_group = 'all' then median_disposable_income_eur end) as median_disposable_income_eur,
        max(case when household_group = 'owner_occupier'
                 then median_disposable_income_eur end)                             as median_disposable_income_owner_eur,
        max(case when household_group = 'all' then households_count end)            as households_count,
        bool_or(is_preliminary)                                                     as is_preliminary
    from staging.stg_cbs__household_income
    where region_type = 'GM'
    group by all
),

cpi as (
    select year, cpi_2025_index
    from staging.stg_cbs__cpi
),

-- 6. Spine = every 2026 municipality x every analysis year, then LEFT JOIN each source. This fixes the
--    grain at 342 x 15 independent of gaps: a missing price or income becomes a NULL (visible, flagged),
--    never a lost row. Years mirror config/cbs_tables.yaml `analysis_years: [2011, 2025]`.
spine as (
    select
        mun.municipality_code,
        yr.year
    from staging.stg_cbs__municipalities_2026 as mun
    cross join (select unnest(range(2011, 2026))::integer as year) as yr
),

joined as (
    select
        s.municipality_code,
        s.year,
        ph.avg_sale_price_eur,
        coalesce(ph.is_harmonised, false)           as is_harmonised,
        i.median_disposable_income_eur,
        i.median_disposable_income_owner_eur,
        i.households_count,
        i.is_preliminary,
        c.cpi_2025_index
    from spine as s
    left join prices_harmonised as ph
        on ph.municipality_code = s.municipality_code and ph.year = s.year
    left join income as i
        on i.municipality_code = s.municipality_code and i.year = s.year
    left join cpi as c
        on c.year = s.year
),

-- 7. Metrics (DATA_DICTIONARY section 3). Division by NULL gives NULL, so missing inputs stay missing.
metrics as (
    select
        *,
        avg_sale_price_eur / median_disposable_income_eur        as price_to_income_ratio,
        avg_sale_price_eur / median_disposable_income_owner_eur  as price_to_income_owner_ratio,
        avg_sale_price_eur * 100 / cpi_2025_index                as real_avg_sale_price_eur_2025,
        median_disposable_income_eur * 100 / cpi_2025_index      as real_median_disposable_income_eur_2025,
        -- Real values in 2025 euro. PTI needs no real variant: price and income share the deflator.
        -- Real growth rates are derived from these columns in the analysis layer / DAX (owner decision 2026-11-26).
        -- growth vs the same municipality's 2011 value (nominal; CPI cancels out of the gap's sign)
        (avg_sale_price_eur
            / max(case when year = 2011 then avg_sale_price_eur end)
                  over (partition by municipality_code) - 1) * 100            as price_growth_since_2011_pct,
        (median_disposable_income_eur
            / max(case when year = 2011 then median_disposable_income_eur end)
                  over (partition by municipality_code) - 1) * 100            as income_growth_since_2011_pct
    from joined
),

-- 8. Flags and ranking (D-009). Flagged rows stay in the table but get no rank.
flags as (
    select
        *,
        price_growth_since_2011_pct - income_growth_since_2011_pct  as growth_gap_pp,
        coalesce(households_count < 5000, false)                    as low_reliability,
        median_disposable_income_eur is null                        as income_missing
    from metrics
),

ranked as (
    select
        *,
        case
            when not low_reliability and not income_missing and price_to_income_ratio is not null
            then rank() over (
                partition by year,
                             (not low_reliability and not income_missing and price_to_income_ratio is not null)
                order by price_to_income_ratio desc
            )
        end                                                          as pti_rank_desc  -- 1 = least affordable
    from flags
)

select
    municipality_code,
    year,
    avg_sale_price_eur,
    median_disposable_income_eur,
    median_disposable_income_owner_eur,
    households_count,
    price_to_income_ratio,
    price_to_income_owner_ratio,
    cpi_2025_index,
    real_avg_sale_price_eur_2025,
    real_median_disposable_income_eur_2025,
    price_growth_since_2011_pct,
    income_growth_since_2011_pct,
    growth_gap_pp,
    pti_rank_desc,
    is_preliminary,
    is_harmonised,
    low_reliability,
    income_missing
from ranked
order by municipality_code, year
