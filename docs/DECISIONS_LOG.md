# Decisions Log

Format: decision · rationale · alternatives · status. Evidence in [`cbs_tables_research.md`](cbs_tables_research.md).
Review of the research PR and the independent checks behind the approvals: [`reviews/2026-11-22_research_review.md`](reviews/2026-11-22_research_review.md).

Status values: **proposed** (written up, awaiting the owner's approval) · **approved** · **approved with changes** (the change is described in the entry) · **deferred** · **rejected**.

## D-001 — House price source: `83625NED`
- **Decision:** Use the average sale price of existing owner-occupied homes (`GemiddeldeVerkoopprijs_1`) from `83625NED`.
- **Rationale:** Only CBS series with prices per municipality per year (1995–2025, all municipalities). The quality-adjusted index `85792NED` covers only NL, LD, PV and the G4.
- **Caveat:** Mean of homes sold, not quality-adjusted; reported in year-specific boundaries.
- **Status:** approved (2026-11-22). Sample values re-checked independently against the API.

## D-002 — Income source: `86380NED` (indeling 2026)
- **Decision:** Use `86380NED` for household income, 2011–2025.
- **Rationale:** Already in the 2026 municipal division for every year (no harmonisation needed), includes medians and owner-occupier breakdown, most recent vintage (2024 final, 2025 preliminary). Population reference date is 1 January of the reporting year (table description).
- **Status:** approved (2026-11-22).

## D-003 — Primary income measure: median disposable household income, excl. students
- **Decision:** Denominator = `MediaanBesteedbaarInkomen_6`, `Populatie = 3000870`, `KenmerkenVanHuishoudens = 1050010`. Mandatory sensitivity: owner-occupier households (`1014800`).
- **Rationale:** Homes are bought by households, so disposable household income (not equivalised) matches ability to pay. The median is robust to top incomes and was stable across table revisions (Amsterdam 2024 mean was revised 60.8 → 58.2, median unchanged at 42.0). Excluding students avoids distorting university cities.
- **Known bias:** the all-households median is pulled down where there are many one-person and renter households (Amsterdam). That is why the owner-occupier PTI is a **mandatory** sensitivity, not an optional one: any G4-vs-rest conclusion must be checked against it.
- **Alternatives:** standardised income (welfare per person, not ability of a household to pay); mean disposable income (revised between vintages, skewed by top incomes).
- **Status:** approved with changes (2026-11-22): owner-occupier sensitivity made mandatory.

## D-004 — Primary metric: price-to-income ratio (PTI)
- **Decision:** `price_to_income_ratio = avg_sale_price_eur / median_disposable_income_eur`. Higher = less affordable.
- **Rationale:** Easy to explain, standard in affordability analysis, unitless (no deflation needed). The mix "mean price / median income" is forced by data availability (no median price per municipality). It makes the level higher than a median/median ratio would be, so the report compares **changes and rankings**, and states this caveat wherever levels are shown.
- **Aggregation:** see D-016 (replaces the "household-weighted ratio of means" in the first draft).
- **Status:** approved with changes (2026-11-22).

## D-005 — Nominal vs real
- **Decision:** PTI in nominal terms; price and income levels/growth also shown in real 2025 euro using the yearly CPI from `86141NED` (2025 = 100).
- **Rationale:** CPI cancels out of the ratio; real values show "prices grew X % above inflation, incomes Y %".
- **Status:** approved (2026-11-22).

## D-006 — Target geography: municipal division of 1 January 2026
- **Decision:** All municipality data mapped to the 342 municipalities of 2026 (`86247NED`).
- **Rationale:** Matches the income table; consistent time series and rankings. The 2027 division (341, Wijdemeren gone) is adopted only when CBS publishes income in the 2027 division.
- **Status:** approved (2026-11-22).

## D-007 — Harmonisation method
- **Decision:** Build a historical → 2026 code mapping by parsing `70739ned/RegioS` descriptions (abolitions + code-changing renames, recursive chains, splits weighted by inhabitants transferred). Sum additive variables; harmonised average price = weighted mean with weight = owner-occupied dwelling stock (`Woningvoorraad_59 * Koopwoningen_64 / 100`, `70072ned`).
- **Rationale:** API-accessible and reproducible. CBS publishes no transaction counts per municipality; owner-occupied stock is the closest concept to "homes that can be sold".
- **Evidence for the weight (owner question 4):** reproducing the official NL average price from the municipal averages (no harmonisation needed in these years) with three weights: 2024 owner stock −1.09 %, total dwellings −0.54 %, households −0.34 %; 2019 owner stock −0.71 %, dwellings +0.71 %, households +1.02 %. No weight is consistently better; all are within ±1.1 %. The weight is therefore chosen on concept (owner stock), and the harmonisation agent reports the impact of the alternatives on the 44 harmonised municipalities.
- **Requirement:** the prototype parser was not committed, so the claim "445 → 342 codes" is not yet reproducible. It must be re-implemented as tested code plus a committed, reviewable mapping file (`data/reference/municipality_mapping_2026.csv`).
- **Alternative:** CBS xlsx "Gemeenten en COROP vanaf 1981" (www.cbs.nl, not reachable from the agent environment) — use as a cross-check if the owner can download it.
- **Status:** approved with changes (2026-11-22).

## D-008 — Analysis window 2011–2025, 2025 flagged
- **Decision:** Use 2011–2025. `is_preliminary` is derived from the CBS `Perioden.Status` field (`Voorlopig`), **not** hard-coded as `year = 2025`. Dashboard KPIs show the latest year with an asterisk and footnote. Every headline insight is re-checked on 2024 (last final year); if the conclusion differs, the report says so.
- **Rationale:** Income starts in 2011; 15 years covers the 2013 trough, the 2022 peak and the 2023 correction. Dropping 2025 would throw away the most recent and most interesting year for employers; deriving the flag from metadata keeps the pipeline correct when CBS finalises 2025 and adds 2026.
- **Base year for growth:** 2011 (first available year), with the full series always shown so that the choice of base year cannot hide the 2013 trough.
- **Status:** approved with changes (2026-11-22).

## D-009 — Gaps and small municipalities
- **Decision:** Keep all municipalities; do not impute. Flag `income_missing` and `low_reliability` (< 5 000 private households, i.e. `ParticuliereHuishoudens_1 < 5`). Flagged rows are **excluded from top/bottom rankings by default**, kept in maps, distributions and aggregates. Power BI gets a slicer "Include small municipalities".
- **Evidence:** 2024: 19 of 342 municipalities have fewer than 5 000 households (95 have fewer than 10 000) — the 5 000 threshold removes the obviously volatile cases without hollowing out the ranking.
- **Rationale:** Imputation would invent data; few transactions make averages volatile (e.g. Vlieland appears in the 2024 top-5).
- **Status:** approved (2026-11-22).

## D-010 — Randstad grouping
- **Decision:** Primary split **G4** (GM0363 Amsterdam, GM0599 Rotterdam, GM0518 's-Gravenhage, GM0344 Utrecht) vs **Rest of NL** (the brief). Secondary three-way split `region_group_3`: `G4` / `Rest of Randstad provinces` (other municipalities in PV26 Utrecht, PV27 Noord-Holland, PV28 Zuid-Holland) / `Rest of NL`. Flevoland (Almere) stays in Rest of NL; documented as a limitation.
- **Rationale:** There is no official CBS municipality list for "the Randstad". Provinces are official and reproducible. The three-way split shows whether unaffordability spills over from the G4 into the surrounding region, which a two-way split cannot show.
- **Extra lens (cheap):** `urbanity_class` from `86247NED` (`Code_54`) is added to `dim_municipality`, so the analysis can test "Randstad effect vs big-city effect" (G4 vs other very strongly urban municipalities).
- **Status:** approved with changes (2026-11-22).

## D-011 — Population/households source: `70072ned`
- **Decision:** Use `70072ned` for population, households, dwelling stock and owner-occupied share (year-specific boundaries, harmonised via D-007).
- **Check (corrected 2026-11-22, stage-2 QA):** the five 2018 gaps in `70072ned` are in the WOZ value (`GemiddeldeWOZWaardeVanWoningen_63`: GM0417, GM0743, GM0847, GM1702, GM1721), not in `Koopwoningen_64`. All 380 municipalities with a price in 2018 have both `Woningvoorraad_59` and `Koopwoningen_64`, so the harmonisation weights are complete; only the WOZ value is missing for these five (see DATA_DICTIONARY 2.3).
- **Precision limitation:** `Koopwoningen_64` is published in whole percentages from 2021 (one decimal before), so the weight is coarser for the 2021–2022 harmonised municipality-years (see DATA_DICTIONARY 2.3, note ²).
- **Status:** approved (2026-11-22).

## D-012 — Mortgage rates and map boundaries
- Superseded by D-013 (Q4 scope) and D-014 (map boundaries).

## D-013 — Q4 (deposit and mortgage) — kept in scope, re-framed
- **Decision:**
  1. **In scope (stage 4):** payment-to-income under a **rate scenario grid** (configurable, e.g. 2–6 % in 0.5 pp steps), 30-year annuity, 100 % LTV of the average price. Needs no external data.
  2. **In scope:** "years of saving for the upfront costs": upfront cost = `upfront_cost_share * avg_sale_price_eur` with a configurable share (purchase costs; transfer tax depends on the buyer, e.g. the starters' exemption), divided by `savings_rate * median_disposable_income_eur`. All parameters in one config file and stated on the dashboard.
  3. **Stretch:** historical mortgage rates (DNB "hypotheekrentes banken" or ECB MIR). Neither host is reachable from the agent environment; the owner downloads the CSV manually and the series ID + download date are recorded here.
  4. **Stretch:** "borrowing gap" = average price − maximum mortgage under the Dutch income-based lending norms — only if the official norm tables can be sourced; no numbers from memory.
- **Rationale:** In the Netherlands the maximum LTV is 100 %, so a "years to save a 10 % deposit" metric misrepresents the Dutch market. The binding constraints are the purchase costs and the income-based borrowing limit. The rate grid answers "how does the rate affect the monthly payment" directly and reproducibly.
- **Alternatives:** the first draft (`deposit_share = 0.10`, `savings_rate = 0.10`) — rejected as arbitrary for NL.
- **Status:** approved (2026-11-22).

## D-014 — Map boundaries: commit a simplified file
- **Decision:** A script (`python -m nl_housing.geo`) downloads `gemeente_gegeneraliseerd` for `jaarcode=2026` from the PDOK OGC API, simplifies it and writes `data/reference/municipalities_2026.geojson` (+ a TopoJSON for the Power BI Shape Map). The simplified file (target < 2 MB) **is committed**, so the dashboard and README maps work without running the download.
- **Verified (2026-11-22, via the collection schema):** properties `statcode`, `statnaam`, `jaarcode`, `jrstatcode`, `rubriek`, `startdatum`, `einddatum`. Join on `statcode` = GM code.
- **Condition:** the licence of the PDOK dataset must be confirmed and attributed in the README before the file is committed. PDOK is not reachable from the agent environment, so the owner runs the script locally.
- **Status:** approved, conditional on the licence check (2026-11-22).

## D-015 — Quality-adjusted index `85792NED`: enable
- **Decision:** Enable `85792NED` (yearly rows `YYYYJJ00` exist for 1995–2025; 21 regions: NL, 4 LD, 12 PV, G4). Uses: (a) compare the trend of the mean price with the quality-adjusted index for the G4 and provinces (is the mean-price trend driven by mix changes?); (b) transaction counts (`VerkochteWoningen_4`) for the G4 and NL, used in D-016.
- **Evidence:** `GemiddeldeVerkoopprijs_7` in `85792NED` equals `GemiddeldeVerkoopprijs_1` in `83625NED` for NL and the G4 (2024: NL 450 985, Amsterdam 617 647, Utrecht 519 924).
- **Status:** approved (2026-11-22).

## D-016 — Aggregation of PTI to groups
- **Decision:**
  - **Provinces and NL:** use CBS's own regional rows (`PVxx`, `NL01`) for both price and median income. No own aggregation.
  - **G4:** the four municipalities individually; a "G4 combined" price = transaction-weighted mean using `85792NED` counts.
  - **Rest of NL price:** exact, from transaction counts: `(price_NL * n_NL - sum(price_g * n_g)) / (n_NL - sum(n_g))` over the G4.
  - **Group median income (G4 combined, Rest of NL, Rest of Randstad provinces):** household-weighted mean of municipal medians, labelled as an approximation.
  - **Rest of Randstad provinces price:** owner-stock-weighted mean (no transaction counts at municipality level); labelled as an approximation.
  - **Distribution view:** median of municipal PTIs per group, as a robust "typical municipality" figure.
- **Validation (mandatory in the marts tests):** the same household-weighted mean of medians over all 342 municipalities reproduces the official NL median within +0.57 % (2011: 32.28 vs 32.1) and +0.80 % (2024: 49.19 vs 48.8). The pipeline must re-run this check for every year and fail if the gap exceeds 2 %.
- **Rationale:** The first draft weighted **prices** by households, which has no conceptual basis; transaction counts are available exactly where the headline comparison (G4 vs rest) needs them.
- **Status:** approved (2026-11-22).

## D-017 — Naming of metrics
- **Decision:** Mart columns follow the CLAUDE.md unit convention: `avg_sale_price_eur`, `median_disposable_income_eur`, `median_disposable_income_owner_eur`, `price_to_income_ratio`, `price_to_income_owner_ratio`, `real_avg_sale_price_eur_2025`, `price_growth_since_2011_pct`, `income_growth_since_2011_pct`, `growth_gap_pp`, `pti_rank_desc`.
- **Status:** approved (2026-11-22).

<!-- D-018…D-021 were proposed in PR #2, D-022…D-025 in PR #4. Both PRs used the numbers D-018…D-021 for
different decisions (stage-2 QA H-2); #2 keeps D-018…D-021 and the proposals of #4 are renumbered D-022…D-025. -->

## D-018 — SQL model order and transactions
- **Decision:** The execution order of the SQL models is an explicit list in `sql/models.yaml`. `make transform` builds all models in one transaction and drops tables in the managed schemas (`staging`, `marts`) that no model produces any more.
- **Rationale:** Numeric file prefixes would break "file name = table name"; a dependency parser is too much machinery for ~10 models. One reviewable list; the runner fails if the list and the folders disagree. One transaction makes a run all-or-nothing; dropping unmanaged tables stops Power BI from reading a stale table of a removed or renamed model.
- **Alternatives:** numeric prefixes (`01_stg_...`); dbt-style dependency inference.
- **Status:** proposed (PR #2; drop of unmanaged tables added in the stage-2 QA follow-up).

## D-019 — Staging drops rows without measures
- **Decision:** Staging drops rows with no measure values in tables that list every historical code for every year (`83625NED`, `70072ned`). Missing municipality-years are detected against the 2026 list downstream (data tests), not kept as NULL rows.
- **Rationale:** CBS returns all 728 GM codes ever used for every year; an all-NULL row means "municipality did not exist that year". Coverage against the 2026 list is asserted separately.
- **Alternatives:** keep the NULL rows and filter in every mart.
- **Status:** proposed (PR #2).

## D-020 — Data tests as SQL files
- **Decision:** Data tests are SQL files in `sql/tests/` that return the violating rows (`make check`). Known exceptions are listed explicitly inside the test, with a reference to the docs.
- **Rationale:** Plain SQL any analyst can read; the output is already the start of the investigation (dbt "singular test" convention). They need the downloaded data, so they run in `make check`, not in the offline `make test`.
- **Alternatives:** pytest against the DuckDB file; Great Expectations / dbt (too heavy for this project).
- **Status:** proposed (PR #2).

## D-021 — `is_preliminary`
- **Decision:** `is_preliminary` = period status `Voorlopig` or `Nader voorlopig`. Any other status fails `make check`. Tables without `is_preliminary` in staging (prices, key figures, price index, CPI) must have only `Definitief` years ≥ 2011 (`assert_period_status_final.sql`).
- **Rationale:** A new CBS status, or a preliminary price year, must not silently count as final.
- **Status:** proposed (PR #2; the check for the other tables added in the stage-2 QA follow-up, P-5).

## D-022 — Mid-year rename: De Fryske Marren 2015
- **Decision:** In 2015 GM1921 and GM1940 both have a price for the same territory. They are combined as one equal-weight unit before weighting, because `70072ned` has 1-January figures for GM1921 only.
- **Status:** proposed (PR #4, as "D-018" there).

## D-023 — Pseudo-municipalities
- **Decision:** GM0998 Buitenland and GM0999 Niet-gemeentelijk ingedeeld are excluded explicitly (`PSEUDO_CODES`) in the herindeling parser and the weight sensitivity.
- **Status:** proposed (PR #4, as "D-019" there).

## D-024 — Boundary corrections are not modelled
- **Decision:** Boundary corrections between existing municipalities are not modelled. Since 2011: 69 transfers, 2 642 inhabitants; the largest relative one is Slochteren → Groningen 2017 (6.6 % of Slochteren), every other transfer is below 3.2 %. Documented as a limitation.
- **Status:** proposed (PR #4, as "D-020" there).

## D-025 — Split weights
- **Decision:** Splits use inhabitant shares at the date of the split, applied to all earlier years, with a uniform price within the split municipality.
- **Status:** proposed (PR #4, as "D-021" there).
