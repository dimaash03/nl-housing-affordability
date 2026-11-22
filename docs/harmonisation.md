# Harmonisation to the municipal division of 1 January 2026

Decisions: D-006 (target = 342 municipalities of 2026), D-007 (method and weights), D-011 (`70072ned`),
D-022 (mid-year rename), D-023 (pseudo-municipalities), D-024 (boundary corrections), D-025 (split weights).
These four were proposed in PR #4 as D-018…D-021 and renumbered (stage-2 QA, H-2).
Code: [`src/nl_housing/harmonise.py`](../src/nl_housing/harmonise.py), [`src/nl_housing/weight_sensitivity.py`](../src/nl_housing/weight_sensitivity.py).
Output: [`data/reference/municipality_mapping_2026.csv`](../data/reference/municipality_mapping_2026.csv) (committed, 456 rows).
All figures below were produced by these two modules on CBS data downloaded on 2026-11-22.

## 1. Why

House prices (`83625NED`) and the key figures used as weights (`70072ned`) are published in the boundaries
of each reporting year: 418 GM codes have a price in 2011, 342 in 2025, 445 different codes over 2011–2025.
Income (`86380NED`) is already in the 2026 division. To compare a municipality over time, every historical
code has to be re-allocated to the 2026 municipality (or municipalities) that now cover its territory.

## 2. The mapping file

One row per (historical code, 2026 code). Every GM code with a price in `83625NED` for 2011–2025 is covered,
including codes that still exist (identity rows), so a single join works for every observation.

| column | meaning |
|---|---|
| `old_code`, `old_name` | historical GM code and its (last) name in `70739ned` |
| `new_code_2026`, `new_name_2026` | municipality on 1 January 2026 (`86247NED`) |
| `weight` | share of the old code allocated to the new code; sums to exactly 1 per `old_code` (6 decimals, rounding absorbed by the largest part) |
| `change_type` | what happened to the **old code**: `unchanged` (still exists; the 2026 municipality may be larger), `rename` (code-changing rename only), `merge` (abolished, whole territory ends in one 2026 municipality, possibly via a chain), `split` (ends in more than one 2026 municipality) |
| `effective_date` | date the old code ceased to exist (first event); empty for `unchanged` |
| `source` | `70739ned RegioS.Description` (+ weight basis for splits) or `86247NED (identity)` |
| `resolution_path` | the chain, e.g. `GM0055>GM1921[2014-01-01]>GM1940[2015-07-01]` (one path per route, `; `-separated) |

`resolution_path` is an addition to the column list in the task brief. It makes every chain reviewable in a diff.

Counts by `old_code`: 342 unchanged, 95 merge, 6 split (17 rows), 2 rename.

### How to use it (pattern for staging/marts)

Column contract: `old_code` ↔ staging `region_code` (historical code, reporting-year boundaries);
`new_code_2026` ↔ `stg_cbs__municipalities_2026.municipality_code` ↔ geo `statcode`. All are trimmed `GMxxxx` strings.
`make load` loads the committed CSV into `reference.municipality_mapping_2026`.

Additive variables (population, households, dwellings):

```sql
select m.new_code_2026, k.year, sum(k.households_count * m.weight) as households_count
from staging.stg_cbs__regional_key_figures as k
join reference.municipality_mapping_2026 as m on m.old_code = k.region_code
where k.region_type = 'GM'
group by all
```

Average price (D-007: weighted mean, weight = owner-occupied stock of the old code × mapping weight), with the one
special case of section 5.2 (D-022): when a renamed code and its successor both have a price in the same year
(only GM1921/GM1940 in 2015), they are one territorial unit: equal-weight mean of the two prices, and the weight
that exists (GM1921's owner stock, as `70072ned` has no 2015 row for GM1940).

<!-- harmonised-price-sql: this block is executed by tests/test_harmonisation_doc_sql.py -->
```sql
with prices as (
    select p.region_code, p.year, p.avg_sale_price_eur, k.owner_occupied_stock
    from staging.stg_cbs__house_prices as p
    left join staging.stg_cbs__regional_key_figures as k using (region_code, year)
    where p.region_type = 'GM'
      and p.region_code not in ('GM0998', 'GM0999')          -- pseudo-municipalities (D-023)
),

renames as (
    select old_code, new_code_2026 from reference.municipality_mapping_2026 where change_type = 'rename'
),

units as (   -- a renamed code priced in the same year as its successor joins the successor's unit (D-022)
    select
        coalesce(r.new_code_2026, p.region_code) as unit_code,
        p.year,
        p.avg_sale_price_eur,
        p.owner_occupied_stock
    from prices as p
    left join renames as r
        on r.old_code = p.region_code
       and exists (select 1 from prices as s where s.region_code = r.new_code_2026 and s.year = p.year)
),

unit_values as (
    select unit_code, year,
           avg(avg_sale_price_eur)   as avg_sale_price_eur,      -- equal weight within the unit
           avg(owner_occupied_stock) as owner_occupied_stock      -- mean of the non-missing weights
    from units
    group by unit_code, year
)

select
    m.new_code_2026,
    u.year,
    sum(u.avg_sale_price_eur * u.owner_occupied_stock * m.weight)
        / sum(u.owner_occupied_stock * m.weight) as avg_sale_price_eur,
    count(distinct u.unit_code)                   as n_source_codes
from unit_values as u
join reference.municipality_mapping_2026 as m on m.old_code = u.unit_code
group by all
order by m.new_code_2026, u.year
```

Without the `units` step (QA H-4), the query silently gives GM1940 2015 = 203 762 instead of 205 512: GM1940's own
2015 price has no weight, so only GM1921's price counts. With it, the query equals the Python reference
`weight_sensitivity.harmonised_prices()` for all 5 130 municipality-years 2011–2025 (checked on the 2026-11-22
download, max abs difference < 1e-6 euro). `tests/test_harmonisation_doc_sql.py` runs this exact block offline on a
small synthetic database (including a mid-year rename) and compares it with the Python reference.
`assert_prices_have_harmonisation_weight.sql` fails if any other priced municipality-year lacks a weight, so the
`left join` cannot hide a new gap.

## 3. Method

1. **Parse** the `Description` of every GM code in `70739ned/RegioS`. Descriptions are blocks separated by a blank
   line (in 5 records by a lone `.`), `\r\n` line endings. Two block types end a code:
   - `Opgeheven per DD-MM-YYYY, overgegaan naar:` followed by one `- <name> (GMxxxx),` line per receiver and a
     `... <ha> hectare met <n> woningen en <n> inwoners` line;
   - `Naamswijziging per DD-MM-YYYY,` + `nieuwe naam: <name> (GMxxxx)` (every rename in the table changes the code).

   Ignored on purpose: `Gemeentelijke herindeling ... ontvangen van` and `Ontstaan ...` (the receiving side of the
   same event), `oude naam:` (the other side of a rename), `Grenswijziging`/`Wijziging` (boundary corrections, see
   section 6) and `Provinciale wijziging`.
2. **Cross-check** every parsed event date against `Einddatum` in the data columns of `70739ned`: 0 mismatches over
   1 131 events, and no code with an `Einddatum` lacks an event.
3. **Allocation weights for splits**: share of inhabitants transferred (fallback dwellings → hectares → equal,
   logged; never needed in 2011–2025). Parts with weight 0 are dropped.
4. **Resolve chains** recursively until the code is in the 2026 list, multiplying the weights. Fails loudly on
   cycles, dead ends, and 2026 codes that also have a terminating event.
5. **Validate**: weights sum to 1 per old code, all targets are in `86247NED`, every price code is covered, no
   duplicate pairs, and the GM codes without an end date in `70739ned` are exactly the 342 codes of `86247NED`.
6. **Pseudo-municipalities excluded** (`PSEUDO_CODES`): GM0998 *Buitenland* (abroad; no end date, so `70739ned` has
   343 active GM codes against 342 in `86247NED`) and GM0999 *Niet-gemeentelijk ingedeeld* (unallocated territory,
   "Opgeheven per 01-01-1996"). They are not parsed as events, cannot enter the mapping, and are left out of the
   boundary-correction count (2 transfers Eijsden-Margraten ↔ abroad in 2018, 0 inhabitants).

Why inhabitants and not dwellings for split weights: it follows D-007 and the brief, and inhabitants are filled
for every receiver. The weight only matters for the 6 splits.

## 4. Reproduction of the research claims (`cbs_tables_research.md` section 5)

| claim | research | reproduced | |
|---|---:|---:|---|
| GM codes with a price in 83625NED 2011–2025 | 445 | 445 | ✔ |
| … resolve to the 2026 list | 342 | 342 | ✔ |
| 2026 municipalities built from one code | 298 | 298 | ✔ |
| 2026 municipalities built from more than one code | 44 | 44 | ✔ |
| abolitions since 2011-01-01 | 117 | 117 | ✔ |
| receiver rows of those abolitions | 129 | 129 | ✔ |
| code-changing renames since 2011 | GM0083→GM1908, GM1921→GM1940, GM0241→GM1945 | same | ✔ |
| splits since 2011 | GM0055 (4), GM0788 (4), GM0140 (3), GM1671 (2), GM0051 (2), GM0053 (2) + GM0424 with a 0-inhabitant part | same | ✔ |
| abolitions by year | 2011: 17, 2015: 13, 2016: 5, others equal | 2011: 16, 2015: 12, 2016: 4 | see note 1 |
| abolished municipalities parsed in total | 823 | 1 069 (883 with receivers, 186 without) | not reproduced, note 2 |

Abolitions by year (reproduced): 2011: 16 · 2012: 4 · 2013: 9 · 2014: 6 · 2015: 12 · 2016: 4 · 2017: 3 · 2018: 11 ·
2019: 34 · 2021: 4 · 2022: 11 · 2023: 3 (total 117).

1. The research by-year list sums to 120, not 117: it counts the 3 renames as well (GM0083 in 2011, GM1921 in 2015,
   GM0241 in 2016). Without them the figures match exactly.
2. The total over all years since 1830 does not reproduce. The table contains 883 `Opgeheven ... overgegaan naar`
   blocks and 186 bare `Opgeheven per ...` lines (no successor listed; the latest is 1935-05-01). Neither is 823.
   The prototype code is not available, so the difference cannot be explained. It has no impact: no pre-2011
   event is needed to resolve a 2011–2025 code.

"Unchanged" in the research means *2026 municipality built from exactly one code*. In the CSV, `unchanged` is
a property of the old code: all 342 codes of 2026 have their own prices, so there are 342 identity rows. Of these,
44 municipalities also receive other codes.

The 44 municipalities built from more than one code (number of source codes): Hoeksche Waard, Land van Cuijk,
De Fryske Marren, Krimpenerwaard, Molenlanden, Westerkwartier (6); Goeree-Overflakkee, Hollands Kroon,
Het Hogeland, Waadhoeke (5); Leeuwarden, Vijfheerenlanden, Eemsdelta, West Betuwe, Altena, Noardeast-Fryslân,
Voorne aan Zee, Meierijstad, Gooise Meren, Berg en Dal, Beekdaelen, Midden-Groningen (4); Groningen, Heerenveen,
Alkmaar, Westerwolde, Schagen, Alphen aan den Rijn, Dijk en Waard, Maashorst, Nissewaard, Súdwest-Fryslân (3);
Amsterdam, Zevenaar, Edam-Volendam, Haarlemmermeer, Noordwijk, Purmerend, Oss, Oisterwijk, Vught, Tilburg,
Boxtel, 's-Hertogenbosch (2). Some of them (Tilburg, Boxtel, Vught, Oss, 's-Hertogenbosch, …) only received
part of a split municipality.

G4: Rotterdam, Den Haag and Utrecht are built from one code. Amsterdam = Amsterdam + Weesp (from 24-03-2022).

## 5. Edge cases

1. **Muiden (GM0424, 2016)** lists two receivers: Gooise Meren (6 206 inhabitants) and Weesp (235 ha, 0 dwellings,
   0 inhabitants). The 0-weight part is dropped. Otherwise it would follow Weesp to Amsterdam with weight 0, and
   Muiden would show up as a "split" for no reason.
2. **De Fryske Marren, mid-year rename (01-07-2015).** `83625NED` has a 2015 price for both GM1921 (De Friese Meren)
   and GM1940. Both map to GM1940 with weight 1. In 2015 the two prices describe the *same territory* in two
   halves of the year, and `70072ned` (reference date 1 January) has 2015 figures for GM1921 only. The price
   calculation therefore treats them as one unit with equal weight, i.e. the simple mean (DATA_DICTIONARY 4.7). This
   is the only such case, logged by `weight_sensitivity`. A sales-count weight would be better, but CBS does not
   publish one per municipality.
3. **Groesbeek (GM0241)** absorbed Millingen aan de Rijn and Ubbergen on 01-01-2015 and kept its code. It was then
   renamed Berg en Dal (GM1945) on 01-01-2016. Chain: `GM0265>GM0241[2015-01-01]>GM1945[2016-01-01]`. GM0241 itself
   is a `rename`, even though its territory grew in 2015 (the code-based mapping does not need to know that).
4. **Weesp (GM0457), abolished mid-year (24-03-2022).** Weesp has a 2022 price, presumably for sales before
   24 March. Whether Amsterdam's 2022 average includes Weesp sales after that date cannot be checked from the
   data. The harmonised 2022 price weights Weesp by its 1-January-2022 owner stock (3.9 % of the combined weight;
   2.0 % with dwellings). Small limitation.
5. **Chains through a split**: e.g. Boarnsterhim (GM0055, 2014): 4 receivers. One of them, De Friese Meren
   (GM1921), was renamed in 2015, so that part reaches GM1940 in two steps.
6. **Rename on 01-01-2011** (GM0083 Menaldumadeel → GM1908 Menameradiel): GM0083 has no price in 2011–2025, so it
   is not in the CSV. GM1908 was abolished into Waadhoeke in 2018.
7. **Text variants handled**: singular `1 woning` / `1 inwoner`, decimal-comma hectares (`0,17 hectare`), a
   missing `met`, detail lines with only hectares + inhabitants or only inhabitants (pre-1990), trailing spaces, a
   lone `.` as block separator. No thousand separators occur; a `.` inside a number is stripped defensively.

Split weights since 2011 (share of inhabitants transferred):

| old code | 2026 municipality: weight |
|---|---|
| GM0051 Skarsterlân (2014) | De Fryske Marren 0.978910 · Heerenveen 0.021090 |
| GM0053 Winsum (2019) | Het Hogeland 0.884635 · Westerkwartier 0.115365 |
| GM0055 Boarnsterhim (2014) | Leeuwarden 0.565972 · Heerenveen 0.308964 · Súdwest-Fryslân 0.084865 · De Fryske Marren 0.040199 |
| GM0140 Littenseradiel (2018) | Súdwest-Fryslân 0.506506 · Leeuwarden 0.317701 · Waadhoeke 0.175793 |
| GM0788 Haaren (2021) | Oisterwijk 0.406970 · Vught 0.342227 · Boxtel 0.150091 · Tilburg 0.100712 |
| GM1671 Maasdonk (2015) | 's-Hertogenbosch 0.592087 · Oss 0.407913 |

## 6. Weight sensitivity of the harmonised average price (D-007)

`python -m nl_housing.weight_sensitivity` computes the harmonised price for every 2026 municipality and year with
three weights from `70072ned` (same year as the price): owner-occupied stock (`Woningvoorraad_59 *
Koopwoningen_64 / 100`, the D-007 choice), total dwellings (`Woningvoorraad_59`) and private households
(`TotaalParticuliereHuishoudens_51`). Statistics are computed over the municipality-years that combine more than one
source code. Elsewhere all weights give the same price.

Harmonised municipality-years (more than one source code): 310 of 5130 (44 municipalities).

| Alternative weight vs owner stock | max abs diff | median abs diff | p95 abs diff | share within 0.5 % | max at |
|---|---:|---:|---:|---:|---|
| dwellings | 3.57 % | 0.23 % | 1.07 % | 76% | Groningen (GM0014) 2012 |
| households | 4.89 % | 0.24 % | 1.30 % | 75% | Groningen (GM0014) 2011 |

Amsterdam incl. Weesp (GM0363), euro:

| year | owner stock | dwellings | households | research prototype (owner stock) |
|---|---:|---:|---:|---:|
| 2019 | 481 422 | 483 026 | 483 138 | 481 422 |
| 2020 | 507 388 | 509 009 | 509 124 | 507 388 |
| 2021 | 564 658 | 567 129 | 567 274 | 564 658 |
| 2022 | 617 736 | 619 256 | 619 349 | 617 736 |

The research prototype values for Amsterdam are reproduced to the euro.

**Interpretation.**
- For a typical harmonised municipality-year the choice of weight moves the price by about 0.2 %. In three
  out of four cases it is within 0.5 %.
- The outlier is **Groningen 2011–2018** (Groningen + Haren + Ten Boer): 3–5 % lower with dwellings or households
  as the weight. Haren's average price in 2011 (346 393) was almost twice the city's (182 373). Its owner-occupied
  share was also much higher (64 % vs 41 %). The weights decide how much Haren counts in 2011: 12.7 % with owner stock,
  8.7 % with dwellings, 6.7 % with households. Only owner-occupied homes are sold in `83625NED`, so Haren's
  larger share of the market is real. This case is the main reason to keep the owner-stock weight.
- After Groningen, no municipality-year differs by more than 1.6 % (Voorne aan Zee 2021, Nissewaard 2012).
- The number of harmonised municipalities falls over time: 44 in 2011, 23 in 2018, 11 in 2019–2020, 6 in 2021,
  2 in 2022, none from 2023. Weight choice cannot affect 2023–2025.

## 7. Limitations

- **Boundary corrections (Grenswijzigingen) are not modelled.** A code is mapped as a whole to its successor.
  Since 2011 there were 69 transfers between municipalities that keep their code, 2 642 inhabitants in total. Only
  3 transfers involved 100+ inhabitants: Nissewaard → Hellevoetsluis 2018 (1 209), Slochteren → Groningen 2017
  (1 033, Meerstad), Haarlemmermeer → Amsterdam 2014 (170). The largest relative effect is Slochteren: 6.6 % of
  its inhabitants (population one year earlier) moved to Groningen. Its 2011–2016 prices still count fully
  towards Midden-Groningen. Hellevoetsluis grew by 3.1 %. Every other transfer is below 0.3 % of the smaller side (four transfers to/from a municipality
  without a population figure for the previous year move 0–5 inhabitants).
  `harmonise.boundary_corrections()` lists every transfer.
- **Uniform price within a split municipality.** A split code contributes its municipal average to every receiver.
  The weight says *how much* of the old municipality went where, not *what* was sold there.
- **Split weights are fixed at the date of the split** and applied to all earlier years. This is acceptable
  because the population of the transferred parts changes slowly.
- **Weights are proxies.** CBS publishes no transaction counts per municipality. Owner stock is the closest concept
  (section 6 quantifies the alternatives).
- **Mid-year changes** (De Fryske Marren 2015, Weesp 2022): see section 5.
- **Owner-share precision from 2021.** `Koopwoningen_64` is published in whole percentages from 2021 (one decimal
  before; DATA_DICTIONARY 2.3), so the owner-stock weight is coarser by up to ±0.5 pp of the dwelling stock. This
  touches only the harmonised municipality-years of 2021 (6) and 2022 (2), including Amsterdam + Weesp in 2022; from
  2023 no municipality needs harmonisation.
- **2027 division**: `86438NED` (341 municipalities) lacks GM1696 Wijdemeren; its successor is not yet in `70739ned`.
  Regenerate the mapping once CBS publishes income in the 2027 division (D-006).
- Cross-check against the CBS xlsx "Gemeenten en COROP vanaf 1981" (D-007 alternative) is still open: www.cbs.nl
  is not reachable from the agent environment.

## 8. Regenerate

```bash
make ingest                                    # needs 70739ned, 83625NED, 70072ned, 86247NED
make harmonise                                 # rebuild the CSV from data/raw/ + load it (review the diff, commit)
make load                                      # loads data/raw/ and the COMMITTED CSV (harmonise --load-only)
python -m nl_housing.weight_sensitivity        # section-6 tables (Markdown on stdout)
```

`make check` runs `assert_mapping_covers_staging.sql`: it fails if the committed CSV no longer fits the staging
data (a priced code without a mapping row, an unknown target, an uncovered 2026 municipality, weights ≠ 1).

The CSV is sorted by `old_code, new_code_2026` with fixed precision, so a CBS update shows up as a readable diff.
