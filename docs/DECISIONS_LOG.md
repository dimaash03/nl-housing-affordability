# Decisions Log

Format: decision · rationale · status. Evidence in [`cbs_tables_research.md`](cbs_tables_research.md).

## D-001 — House price source: `83625NED`
- **Decision:** Use the average sale price of existing owner-occupied homes (`GemiddeldeVerkoopprijs_1`) from `83625NED`.
- **Rationale:** Only CBS series with prices per municipality per year (1995–2025, all municipalities). The quality-adjusted index `85792NED` covers only NL, LD, PV and the G4.
- **Caveat:** Mean of homes sold, not quality-adjusted; reported in year-specific boundaries.
- **Status:** proposed — needs owner approval.

## D-002 — Income source: `86380NED` (indeling 2026)
- **Decision:** Use `86380NED` for household income, 2011–2025.
- **Rationale:** Already in the 2026 municipal division for every year (no harmonisation needed), includes medians and owner-occupier breakdown, most recent vintage (2024 final, 2025 preliminary).
- **Status:** proposed — needs owner approval.

## D-003 — Primary income measure: median disposable household income, excl. students
- **Decision:** Denominator = `MediaanBesteedbaarInkomen_6`, `Populatie = 3000870`, `KenmerkenVanHuishoudens = 1050010`. Sensitivity: owner-occupier households (`1014800`).
- **Rationale:** Homes are bought by households, so disposable household income (not equivalised) matches ability to pay. The median is robust to top incomes and was stable across table revisions (Amsterdam 2024 mean was revised 60.8 → 58.2, median unchanged at 42.0). Excluding students avoids distorting university cities (Amsterdam, Utrecht, Groningen, …).
- **Status:** proposed — needs owner approval.

## D-004 — Primary metric: price-to-income ratio (PTI) = average price / median disposable household income
- **Decision:** PTI as the headline affordability metric; aggregates computed as household-weighted ratio of means, never an unweighted mean of municipal ratios.
- **Rationale:** Easy to explain, standard in housing affordability analysis, unitless (no deflation needed). The mix "mean price / median income" is forced by data availability (no median price per municipality) and must be stated in the report.
- **Status:** proposed — needs owner approval.

## D-005 — Nominal vs real
- **Decision:** PTI in nominal terms; price and income levels/growth also shown in real 2025 euro using the yearly CPI from `86141NED` (2025 = 100).
- **Rationale:** CPI cancels out of the ratio; real values help to show "prices grew X % above inflation, incomes Y %".
- **Status:** proposed — needs owner approval.

## D-006 — Target geography: municipal division of 1 January 2026
- **Decision:** All municipality data mapped to the 342 municipalities of 2026 (`86247NED`).
- **Rationale:** Matches the income table; allows consistent time series and rankings. The 2027 division (341, Wijdemeren gone) can be adopted when CBS publishes income in the 2027 division.
- **Status:** proposed — needs owner approval.

## D-007 — Harmonisation method
- **Decision:** Build a historical → 2026 code mapping by parsing `70739ned/RegioS` descriptions (abolitions + code-changing renames, recursive chains, splits weighted by inhabitants transferred). Sum additive variables; compute harmonised average price as a weighted mean using owner-occupied dwelling stock (`Woningvoorraad_59 * Koopwoningen_64 / 100`, `70072ned`).
- **Rationale:** API-accessible and reproducible; prototype resolved all 445 historical codes (2011–2025) to the 2026 list. CBS publishes no transaction counts per municipality, so owner-occupied stock is the best available proxy for the number of sales.
- **Alternative:** CBS xlsx "Gemeenten en COROP vanaf 1981" (www.cbs.nl, not reachable here).
- **Status:** proposed — needs owner approval.

## D-008 — Analysis window 2011–2025
- **Decision:** Use 2011–2025; flag 2025 as preliminary (`is_preliminary`).
- **Rationale:** Income series starts in 2011; 15 years meets the "10+ years" goal and covers the 2013 trough, the 2022 peak and the 2023 correction.
- **Status:** proposed — needs owner approval.

## D-009 — Gaps and small municipalities
- **Decision:** Keep all municipalities; do not impute. Flag `income_missing` (3 municipalities in 2025) and `low_reliability` (< 5 000 households). Exclude flagged rows from top/bottom rankings by default, keep them in maps.
- **Rationale:** Imputation would invent data; small municipalities (Wadden islands, Rozendaal) have few transactions and volatile averages.
- **Status:** proposed — needs owner approval.

## D-010 — Randstad grouping
- **Decision:** Primary split G4 (GM0363 Amsterdam, GM0599 Rotterdam, GM0518 's-Gravenhage, GM0344 Utrecht) vs rest of the Netherlands; optional second split by province (PV26 Utrecht, PV27 Noord-Holland, PV28 Zuid-Holland vs others).
- **Rationale:** Matches the brief; the province split gives a wider "Randstad region" view without inventing a custom definition.
- **Status:** proposed — needs owner approval.

## D-011 — Population/households source: `70072ned`
- **Decision:** Use `70072ned` for population, households, dwelling stock and owner-occupied share (year-specific boundaries, harmonised via D-007).
- **Rationale:** One table covers all needed context variables and the harmonisation weights. `71486ned` and `03759ned` are verified fallbacks.
- **Status:** proposed — needs owner approval.

## D-012 — Out of scope for now: mortgage rates and maps download
- **Decision:** Document DNB mortgage rates and PDOK boundaries only; do not ingest yet.
- **Rationale:** Hosts not reachable from the research environment; DNB series ID not verified. Optional question Q4 depends on it.
- **Status:** proposed — needs owner approval.
