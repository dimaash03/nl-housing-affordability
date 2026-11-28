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
- **Status:** approved (PR #2; drop of unmanaged tables added in the stage-2 QA follow-up).

## D-019 — Staging drops rows without measures
- **Decision:** Staging drops rows with no measure values in tables that list every historical code for every year (`83625NED`, `70072ned`). Missing municipality-years are detected against the 2026 list downstream (data tests), not kept as NULL rows.
- **Rationale:** CBS returns all 728 GM codes ever used for every year; an all-NULL row means "municipality did not exist that year". Coverage against the 2026 list is asserted separately.
- **Alternatives:** keep the NULL rows and filter in every mart.
- **Status:** approved (PR #2).

## D-020 — Data tests as SQL files
- **Decision:** Data tests are SQL files in `sql/tests/` that return the violating rows (`make check`). Known exceptions are listed explicitly inside the test, with a reference to the docs.
- **Rationale:** Plain SQL any analyst can read; the output is already the start of the investigation (dbt "singular test" convention). They need the downloaded data, so they run in `make check`, not in the offline `make test`.
- **Alternatives:** pytest against the DuckDB file; Great Expectations / dbt (too heavy for this project).
- **Status:** approved (PR #2).

## D-021 — `is_preliminary`
- **Decision:** `is_preliminary` = period status `Voorlopig` or `Nader voorlopig`. Any other status fails `make check`. Tables without `is_preliminary` in staging (prices, key figures, price index, CPI) must have only `Definitief` years ≥ 2011 (`assert_period_status_final.sql`).
- **Rationale:** A new CBS status, or a preliminary price year, must not silently count as final.
- **Status:** approved (PR #2; the check for the other tables added in the stage-2 QA follow-up, P-5).

## D-022 — Mid-year rename: De Fryske Marren 2015
- **Decision:** In 2015 GM1921 and GM1940 both have a price for the same territory. They are combined as one equal-weight unit before weighting, because `70072ned` has 1-January figures for GM1921 only.
- **Status:** approved (PR #4, as "D-018" there).

## D-023 — Pseudo-municipalities
- **Decision:** GM0998 Buitenland and GM0999 Niet-gemeentelijk ingedeeld are excluded explicitly (`PSEUDO_CODES`) in the herindeling parser and the weight sensitivity.
- **Status:** approved (PR #4, as "D-019" there).

## D-024 — Boundary corrections are not modelled
- **Decision:** Boundary corrections between existing municipalities are not modelled. Since 2011: 69 transfers, 2 642 inhabitants; the largest relative one is Slochteren → Groningen 2017 (6.6 % of Slochteren), every other transfer is below 3.2 %. Documented as a limitation.
- **Status:** approved (PR #4, as "D-020" there).

## D-025 — Split weights
- **Decision:** Splits use inhabitant shares at the date of the split, applied to all earlier years, with a uniform price within the split municipality.
- **Status:** approved (PR #4, as "D-021" there).

## D-026 — Definition of `is_harmonised`
- **Decision:** `is_harmonised` is TRUE when the municipality-year price was built from more than one CBS source row (historical code), including the 2015 GM1921/GM1940 rename pair. 311 of 5 130 rows; the weight sensitivity reports 310 because it counts territorial units.
- **Rationale:** The flag tells the dashboard user that a value is derived, not read directly from CBS. GM1940 2015 is the mean of two CBS rows, so it is derived.
- **Alternatives:** count territorial units (310 rows) — consistent with `weight_sensitivity`, but would label a combined value as raw.
- **Status:** approved (owner, 2026-11-26).

## D-027 — Real values in the fact, real growth downstream
- **Decision:** `fct_affordability` holds `cpi_2025_index`, `real_avg_sale_price_eur_2025` and `real_median_disposable_income_eur_2025`. Real growth rates and a real growth gap are computed from these columns in the notebooks / DAX; the fact keeps nominal growth columns only.
- **Rationale:** One deflation definition shared by Python and Power BI; the fact stays row-level. PTI needs no real variant because price and income share the deflator.
- **Alternatives:** all real growth columns in the fact (wider table, duplicated logic); deflate only in DAX (two definitions).
- **Status:** approved (owner, 2026-11-26).

## D-028 — Province columns denormalised into `dim_municipality`
- **Decision:** `dim_municipality` carries `province_code` and `province_name`; `dim_province` exists as a separate dimension for province-level facts (group aggregates). Provinces follow the 2026 division for every year.
- **Rationale:** A municipality never changes province within this model (2026 division), so copying two columns costs nothing and keeps the Power BI model a pure star: one relationship per fact key, no snowflake chain fact → municipality → province, which would force bidirectional filters or extra relationships.
- **Alternatives:** snowflake (`dim_municipality` → `dim_province`), cleaner normalisation but a harder Power BI model; province only in `dim_province`.
- **Status:** approved (owner merged PR #10, 2026-11-26).

## D-029 — Rest of Randstad provinces price: exact residual
- **Decision:** The price of "Rest of Randstad provinces" is the exact residual `(PV26 + PV27 + PV28) minus G4` with `85792NED` average prices and transaction counts, like Rest of NL. Replaces the owner-stock-weighted approximation in D-016.
- **Rationale:** `85792NED` publishes counts for the 12 provinces, so the exact value is available at no extra cost; an exact figure is easier to defend than an approximation. `assert_group_aggregates.sql` checks that `85792NED` and `83625NED` agree on NL and province prices (they do, to the euro), that counts add up to NL and that G4 + Rest recombine to the NL price.
- **Alternatives:** owner-stock-weighted mean of harmonised municipal prices (needs a harmonised stock per 2026 municipality; approximate).
- **Limitation:** `85792NED` reports each year in that year's boundaries, so Weesp is outside the G4 price before 2022.
- **Status:** proposed (PR: group aggregates + export).

## D-030 — "Latest year" flags follow the loaded data
- **Decision:** `dim_year.is_latest_year` (= last year of the configured window) is replaced by `is_latest_data_year` = last year in which at least one municipality has a PTI, and `is_latest_final_year` uses the same rule restricted to final income. `dim_year` also gets `has_price_data`, `has_income_data`, `has_pti_data` and `municipalities_with_pti`.
- **Rationale:** A flag called "latest" must not point at a year without data. With the old rule, a configured but not yet published (or not loaded) year would become the default year of every "latest" card in Power BI and show blanks. Tested by blanking the 2025 income in a copy of the database: the flags move to 2024. The column is renamed rather than redefined, so nobody reads the old meaning into the old name.
- **Alternatives:** keep `is_latest_year` and redefine it (silent change of meaning); require both price and income per municipality (stricter, but one suppressed small municipality would then never block a year — `has_pti_data` already means "a ratio exists").
- **Status:** proposed (PR: review follow-ups 2026-11-27).

## D-031 — `config/cbs_tables.yaml` is the single source of truth for analysis parameters
- **Decision:** `nl_housing.transform` writes the `project:` section (analysis window, base year = first year, G4 codes, Randstad provinces, low-reliability threshold) to the one-row table `reference.project_settings` before the models run; staging, marts and data tests read it from there. No year range or code list is repeated in model SQL.
- **Rationale:** Before, the window `2011–2025` was a literal in 10+ places while the comments pointed at the config, which nothing read. A table instead of SQL templating keeps every model a plain, runnable SELECT (no Jinja) and lets the data tests see the same values.
- **Kept as literals on purpose:** the agreed group rules in `sql/tests/assert_region_groups.sql` (G4, PV26–28, group sizes 4 / 116 / 222). A test that reads the expected values from the same config cannot catch a wrong config. The growth columns are still named `*_since_2011_*` (D-017); `assert_project_settings.sql` fails if the base year changes without renaming them.
- **Verified:** rebuilding with the new code reproduces every staging and marts table of `main` (identical rows; `fct_affordability` floats equal to 1e-10 EUR — summation order changed with the query plan); a rebuild with window 2013–2024 gives 342 × 12 rows and fails only the base-year naming guard, as intended.
- **Alternatives:** Jinja / dbt variables (more machinery for 5 parameters); keep literals and add a test that greps the SQL (catches drift, but still two places to edit).
- **Status:** proposed (PR: review follow-ups 2026-11-27).

## D-032 — Minimum Python 3.11 / DuckDB 2.x
- **Decision:** `requires-python >= 3.11`, `duckdb >= 2.0.1`.
- **Rationale:** On Python 3.10 pip resolves DuckDB 1.5.6 (DuckDB 2.x ships no 3.10 wheels), and DuckDB 1.x cannot plan `fct_affordability` ("Not implemented Error: Cannot perform non-inner join on subquery"); the README promised 3.10+. Verified 2026-11-27: Python 3.11 with the newest versions allowed by `requirements.txt` runs the full build (12 models, 21/21 checks) and all 174 unit tests; CI runs that combination on every PR.
- **Alternatives:** rewrite the correlated `exists` in `fct_affordability` for DuckDB 1.x (keeps 3.10, but pins the project to an old engine).
- **Status:** proposed (PR: review follow-ups 2026-11-27).

## D-033 — Findings are rendered from code and guarded by asserts
- **Decision:** In `notebooks/01_affordability_findings.ipynb` every finding is a code cell that renders Markdown from the computed numbers (f-strings). The words that carry a claim ("rose", "widest", "only", "mostly", "holds") are guarded by `assert`s placed directly above the text. The notebook is committed **with** outputs so GitHub shows the findings and charts.
- **Rationale:** Typed-in numbers go stale silently after a CBS revision or a model change; an assert makes the notebook stop instead of printing a false sentence. During development this caught one wrong sentence (the G4 growth lead was described as holding in the preliminary year; it halves). Committed outputs make the notebook readable for a reviewer who does not run it.
- **Alternatives:** Markdown cells with typed numbers (simplest, unguarded); a templating step (papermill/Quarto), more machinery for one notebook. `ruff` E501 is relaxed for notebooks only (`pyproject.toml`), because the formatter cannot wrap prose inside f-strings.
- **Update 2026-11-28 (EDA review, point 6):** the README *Key insights* were typed by hand in PR #13 and could drift from the notebook. Now section 6 of the notebook renders them and `nl_housing.report.write_key_findings` writes the same text to `docs/KEY_FINDINGS.md` and between the `key-findings` markers in `README.md`. Guards: `tests/test_report.py` fails if the README block and the file differ (hand edit); the CI `pipeline` job runs `make reproduce && make notebook` on fresh CBS data and fails on any diff in either file (CBS revision) and on any failing assert. Figures are regenerated by the same run but not diffed (PNG bytes differ between font renderers). `make notebook` runs the notebook headless (`nbconvert --execute --inplace`, no timing metadata); the last cell closes the DuckDB connection so an open kernel no longer blocks `make build`.
- **Status:** proposed (PR: stage 4 analysis notebook); update proposed (PR: EDA review follow-ups).

## D-034 — Owner-occupier group income (built in the notebook, stored in the mart since stage 5)
- **Decision:** The owner-occupier sensitivity for groups (G4, Rest of Randstad provinces, Rest of NL) uses the owner-occupier-household-weighted mean of the municipal owner-occupier medians (`staging.stg_cbs__household_income`, `household_group = 'owner_occupier'`); NL uses the published median. The same validation as D-016 runs first: over all municipalities the approximation is +0.38 … +0.65 % from the published NL owner-occupier median (limit 2 %), and the notebook asserts it.
- **Rationale:** Same method as the main group income (D-016), so the two PTIs differ only in the income definition. It is a sensitivity, not a reported metric, so it stays in the analysis layer rather than in `fct_group_affordability`.
- **Alternatives:** weight by all households (wrong weight for an owner-only median); add owner columns to the mart (move there if Power BI needs them).
- **Update 2026-11-28 (stage 5, owner decision in D-038):** Power BI needs the owner-occupier group income for the income-basis switch, so it moved into `marts.fct_group_affordability` (`median_disposable_income_owner_eur`, `price_to_income_owner_ratio`, `owner_households_count`, `income_owner_method`; NL and provinces: published CBS owner-occupier median). `fct_affordability` gained `owner_households_count` (the weight) and `pti_owner_rank_desc`. The 2 % validation is now also a SQL check (`assert_owner_income_weighted_median_vs_nl`, +0.38 … +0.65 %). The notebook still rebuilds the income from the municipal rows and asserts it equals the mart, so the method stays visible and the two cannot drift; its outputs and `docs/KEY_FINDINGS.md` are unchanged.
- **Status:** proposed (PR: stage 4 analysis notebook); updated in the stage 5 PR.

## D-035 — Rank changes on a fixed panel; persistence as Spearman rank correlation
- **Decision:** Rank *changes* between two years are computed on the panel of municipalities ranked (D-009) in both years, re-ranked within that panel. Persistence of the ranking = Spearman rank correlation (Pearson correlation of ranks; no scipy dependency).
- **Rationale:** The ranked set changes over time (Laren and Blaricum pass 5 000 households after 2011), so a rank out of 316 and a rank out of 323 are not comparable. Spearman needs no assumption about the PTI distribution and answers "is the order the same?".
- **Alternatives:** compare raw `pti_rank_desc` across years (mixes set changes into rank changes); percentile ranks (comparable across set sizes, but harder to read than "rank 5 of 316").
- **Status:** proposed (PR: stage 4 analysis notebook).

## D-036 — Robustness verdict rule
- **Decision:** Each claim is re-measured under each check and classified: **holds** = same direction and at least half the size; **weaker** = same direction, less than half the size; **reverses** = opposite direction. Threshold-type claims state their own rule (share of suburbs in the top 25 ≥ 50 %; Spearman ≥ 0.7 holds, ≥ 0.5 weaker; ≥ 3 of 4 G4 cities in the least-affordable third). Section 4 shows all results in one matrix; every *weaker* / *reverses* result is named in the finding text.
- **Rationale:** A fixed, written rule stops the analyst from calling a halved effect "robust". 50 % is a judgement call, stated openly; the raw baseline and variant values are shown next to every verdict so a reader can apply another threshold.
- **Alternatives:** statistical significance tests (the data are a full population of municipalities, not a sample; a p-value answers a different question); free-text robustness notes (not comparable across findings).
- **Update 2026-11-28 (EDA review, points 2–3):**
  - *The rule is an editorial heuristic*, written down before the checks were read, not a statistical test (the data are the full population of municipalities: there is no sampling error to test). Section 4.1 re-labels every check under a **lenient** rule (¼ of the size; levels 0.4 / 0.6 / 2 G4 cities / 80 %) and a **strict** rule (¾; levels 0.6 / 0.8 / 4 G4 cities / 95 %). Build of 2026-11-28: lenient 25 hold / 1 weaker / 0 reverse, default 21 / 4 / 1, strict 17 / 8 / 1; 9 of 26 labels depend on the rule. The finding texts state baseline and variant values and their asserts test magnitudes, so no sentence depends on the rule.
  - *Checks are typed*: alternative specification (owner-occupier income, typical municipality, quality-adjusted index, small municipalities included), data vintage (preliminary year), data-quality control (harmonised municipalities removed), and identity (real vs nominal: one CPI factor, mathematically bound to agree). Identities are shown but not counted, so PR #13's "32 checks" becomes 26 evidence checks + 6 identities. The counts describe re-measurements of the same CBS data, not independent confirmations.
- **Status:** proposed (PR: stage 4 analysis notebook); update proposed (PR: EDA review follow-ups).

## D-037 — Sub-period break points come from the data
- **Decision:** Section 3 splits 2011–2024 at the national PTI low before the peak (2013), the peak of the G4 / Rest of NL PTI ratio (2019) and the national PTI peak (2022), all computed with `idxmin` / `idxmax`.
- **Rationale:** Periods picked by eye invite the question "why those years?"; data-driven break points have a one-line answer and move automatically if the data change.
- **Alternatives:** fixed calendar periods (e.g. 5-year blocks), which cut through turning points; external events (rate changes) — no rate data in the project yet (D-013).
- **Status:** proposed (PR: stage 4 analysis notebook).

## D-038 — Income basis is explicit in every headline and on the dashboard
- **Decision:** The all-household PTI stays the primary metric (D-003), but it is always labelled as prices relative to the income of **all residents** (renters included), never as a measure for buyers. Every headline is published next to its owner-occupier version: the README block has a "Headline by income basis" table and a "How to read the PTI" paragraph (owner-occupier share: 36 % of households in the G4, 62 % elsewhere, build of 2026-11-28). Axis labels say "average sale price ÷ median household income", not "years of income". Dashboard requirements are in `powerbi/README.md` (*Income basis*).
- **Rationale:** Owner-occupier income changes the size of the G4 gap (1.39× → 1.11×) and reverses one claim (G4 cities in the least-affordable third: 4 → 1 of 4). A reader who sees only the all-household PTI would read a resident-mix effect as a price effect.
- **Owner decisions (2026-11-28):** (1) dashboard default income basis = **all households** (CBS-standard, comparable with other sources), with a visible switch to owner-occupiers; (2) the owner-occupier **group** income moves into `fct_group_affordability` with the same 2 % validation test (done in the stage 5 PR, see D-034).
- **Alternatives:** make owner-occupier income the primary metric (closer to buyers, but leaves out the renters for whom affordability is the barrier, and owners are not buyers either); show only the all-household PTI with a footnote (the footnote is what readers skip).
- **Status:** approved 2026-11-28 (owner); implementation in the stage 5 PR (`powerbi/README.md`, *Income basis*).

## D-039 — Power BI model as code (PBIP / TMDL), income basis as a disconnected switch table
- **Decision:** The dashboard is a Power BI Project (`powerbi/nl_housing_affordability.pbip`) with the semantic model in TMDL and the report in PBIR, not a binary `.pbix`. The mart tables' TMDL is generated from the exported Parquet files (`python -m nl_housing.powerbi scaffold`, never overwriting a file Desktop has saved); measures, relationships and the switch table are hand-written. `make check-powerbi` (part of `make build` and the CI pipeline job) fails on a mart column missing from the model, a type mismatch, or a DAX reference to a table, column or measure that does not exist. `powerbi/CHECKS.md` lists control values for the key measures, computed independently in SQL (`python -m nl_housing.powerbi expected`); CI fails when fresh data changes them. The income basis is a two-row disconnected table (`'Income basis'`) read by every PTI, income, rank and growth measure through `SWITCH`-style branching; no selection = all households (D-038). Ratio measures return a value only for exactly one fact row, and the report year defaults to the latest final year.
- **Rationale:** A `.pbix` is a zip that git cannot diff: a reviewer (or an interviewer) cannot see what changed in a measure. TMDL makes the model reviewable and testable without Windows. A field parameter would only swap fields inside a visual; the switch must also drive measures built on other measures (rank change, G4 ÷ rest, share of municipalities), map colours and subtitles, which a disconnected table does with one code path. Blank-above-grain ratio measures make it impossible to show an average of municipal PTIs as a group value (D-016).
- **Alternatives:** `.pbix` only (simplest, but no diff and no automated check); field parameter for the switch (cannot feed other measures or conditional formatting); DuckDB ODBC in DirectQuery (needs a driver in the VM, slower, and the marts are small enough to import); computing ranks and panel rank changes only in SQL (ranks are in the mart; the panel rank change depends on the selected year pair, so it is a measure).
- **Limitations:** the TMDL was written and checked outside Power BI (JSON schemas, `check-powerbi`), but not yet opened in Desktop; the first open and the CHECKS.md comparison are the acceptance test. After Desktop's first save, Desktop is the editor of the model; the scaffold is only for new mart tables.
- **Status:** proposed (PR: stage 5 Power BI model).
