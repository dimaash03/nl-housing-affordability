# CBS Tables Research

Date of verification: **2026-11-14**. Method: direct queries to the CBS OData API
(`https://opendata.cbs.nl/ODataApi/odata/<id>/` and the paged `ODataFeed` endpoint), the CBS catalog
(`https://opendata.cbs.nl/ODataCatalog/Tables`, 5 986 tables) and the new catalog on `datasets.cbs.nl`.
Hosts `www.cbs.nl`, `service.pdok.nl` and `api.pdok.nl` were **not reachable** from the research environment;
sources on those hosts are documented from web search results only and marked as not verified.

Everything below marked "verified" was returned by the API. Nothing was assumed from memory.

**Re-check 2026-11-22:** table metadata (`Modified`, `Period`) of all chosen tables is unchanged, except `86247NED` (modified 2026-11-17: final figures for centre municipalities and police units added). All 13 column keys used from `86247NED` still exist and the list still has 342 municipalities; only the formatting of 8 municipality names changed (e.g. `Bergen (NH.)` → `Bergen (NH)`, `Beek (L.)` → `Beek (LI)`). **Join on codes, never on names.**

## 0. Summary

| Need | Chosen table | Coverage | Boundaries | Status |
|---|---|---|---|---|
| a) Average house price | `83625NED` | 1995–2025 | year of reporting | verified |
| b) Household income | `86380NED` | 2011–2025 (2025 preliminary) | **2026 division, all years** | verified |
| c) Population, households, dwellings | `70072ned` | 1995–2026 (columns vary) | year of reporting | verified |
| d) CPI | `86141NED` (yearly averages) | 2010–2025 | national | verified |
| e) Municipal reorganisations | `70739ned` (RegioS descriptions) + `86247NED` (2026 list) | 1830–2026 | — | verified, parser prototyped |
| f) Boundaries for maps | PDOK OGC API `cbs/gebiedsindelingen` | 2016+ (historic 1995–2015) | per `jaarcode` | documented, not verified |
| g) Mortgage rates | DNB statistics (residential mortgages dashboard) | — | national | documented, series ID not verified |

## 1. House prices — `83625NED` (verified)

- Title: *Bestaande koopwoningen; gemiddelde verkoopprijzen, regio* / *Existing own homes; average purchase prices, region* (83625ENG).
- Modified 2026-02-17; period "1995 t/m 2025"; frequency yearly.
- One measure: `GemiddeldeVerkoopprijs_1` (euro, 0 decimals). Dimensions `RegioS`, `Perioden`.
- 745 regions: NL01, 4 LD, 12 PV, 728 GM. Total 23 095 rows → more than the 10 000-row limit of `ODataApi`; use `ODataFeed`.
- **Each year uses that year's boundaries.** Non-null GM values per year: 2011: 418, 2015: 394, 2019: 355, 2022: 345, 2023–2025: 342.
  Non-null GM sets match the municipalities in `70072ned` for every year 2011–2025, except 2015 (see edge case below).
- Example of the boundary issue: Weesp (GM0457) is still published separately in 2022 (merged into Amsterdam on 24-03-2022).

Sample (euro):

| Year | Amsterdam GM0363 | Utrecht GM0344 | Netherlands NL01 |
|---|---|---|---|
| 2011 | 284 668 | 255 878 | 240 059 |
| 2013 | 256 308 | 231 691 | 213 353 |
| 2015 | 303 925 | 245 900 | 230 194 |
| 2020 | 510 919 | 405 791 | 334 488 |
| 2022 | 620 954 | 510 980 | 428 591 |
| 2023 | 568 161 | 474 406 | 416 153 |
| 2024 | 617 647 | 519 924 | 450 985 |
| 2025 | 630 621 | 549 113 | 479 527 |

Caveats (from the table metadata):
- Mean price of the homes **sold in that year**, not quality-adjusted. CBS states explicitly that the average price is *not* an indicator of price development, because the mix of homes sold changes. For price **trends**, the quality-adjusted index `85792NED` (PBK) exists, but only for NL/LD/PV and the G4 cities.
- Purchases by private persons only; existing homes only (no new-build).
- Final at first publication; no regular revisions. Kadaster's own figures can differ slightly.
- Small municipalities have few transactions → volatile averages.
- **Edge case:** 2015 has two rows for De Fryske Marren: GM1921 (old name, 203 762) and GM1940 (new name from 01-07-2015, 207 262). Both map to GM1940; without transaction counts use a simple mean (or the GM1940 value).

## 2. Household income — `86380NED` (verified, recommended)

- Title: *Inkomen van huishoudens; huishoudenskenmerken, regio (indeling 2026)*. New table (Oct 2026), successor of `86161NED` (indeling 2025).
- Period 2011–2025; `Perioden` status: 2011–2024 `Definitief`, 2025 `Voorlopig`.
- **Regions: 342 GM in the 1 January 2026 division for every year** (+ NL01, 4 LD, 12 PV, 40 CR, 35 AM). This removes the need to harmonise income.
- Dimensions: `Populatie` (`1050010` incl. students, `3000870` excl. students), `KenmerkenVanHuishoudens` (25 values, incl. `1050010` all households, `1014800` owner-occupiers, `1014850` tenants, household type, age of main earner, income source).
- Measures: `ParticuliereHuishoudens_1` (x 1 000), `ParticuliereHuishoudensRelatief_2` (%), `GemiddeldGestandaardiseerdInkomen_3`, `MediaanGestandaardiseerdInkomen_4`, `GemiddeldBesteedbaarInkomen_5`, `MediaanBesteedbaarInkomen_6` (all 1 000 euro), plus decile shares `..._7` to `..._16` (%).
- Coverage (Populatie `3000870`, GM level): all 342 municipalities filled for 2011–2024 for all four income measures, both for all households and owner-occupiers. 2025: median disposable income missing for 3 municipalities (GM0088 Schiermonnikoog, GM0096 Vlieland, GM0277 Rozendaal; 600–700 households each).

Sample — all private households excl. students (1 000 euro):

| Year | Median disposable: AMS / UTR / NL | Mean disposable: AMS / UTR / NL | Median standardised: AMS / UTR / NL |
|---|---|---|---|
| 2011 | 25.5 / 29.4 / 32.1 | 33.3 / 35.9 / 37.5 | 20.8 / 23.2 / 23.2 |
| 2015 | 27.6 / 31.8 / 33.4 | 36.9 / 39.3 / 39.6 | 22.5 / 25.4 / 24.7 |
| 2020 | 33.1 / 37.8 / 38.9 | 46.0 / 47.4 / 47.5 | 27.2 / 30.5 / 29.1 |
| 2024 | 42.0 / 47.7 / 48.8 | 58.2 / 60.2 / 59.9 | 35.0 / 38.6 / 37.0 |
| 2025* | 43.7 / 49.5 / 50.7 | 60.4 / 62.7 / 62.2 | 36.5 / 40.2 / 38.6 |

\* preliminary. Owner-occupier households, median disposable (AMS / UTR / NL): 2011 42.5 / 44.4 / 41.6; 2024 72.5 / 77.8 / 66.3.

Caveats:
- **Revisions between table vintages.** The 2024 *mean* disposable income for Amsterdam was 60.8 in `86161NED` (2024 preliminary) and is 58.2 in `86380NED` (2024 final); Utrecht 61.1 → 60.2. The *medians* did not change (42.0 and 47.7). Medians are more robust to revisions and to very high incomes.
- Median of a municipality cannot be re-aggregated to provinces/groups; use CBS's own PV/NL rows or a household-weighted mean of medians (label it as such).
- Amsterdam's low median disposable income partly reflects many one-person households; standardised income corrects for this, but a home is bought by a household, so disposable income is the closer match to "ability to pay".
- New tables appear each autumn with a new division ("indeling 2027" etc.). The ID will change; config must be updated yearly.

## 3. Population and households — `70072ned` (verified)

- Title: *Regionale kerncijfers Nederland*; period "Jaarcijfers 1995 - 2026"; 785 regions (728 GM codes, year-specific boundaries).
- Verified keys and fill rate at GM level (2010–2026): `TotaleBevolking_1` filled 2010–2026; `TotaalParticuliereHuishoudens_51`, `GemiddeldeHuishoudensgrootte_58`, `Woningvoorraad_59`, `Koopwoningen_64` filled 2010–2025 (Koopwoningen has 5 gaps in 2018 — review 2026-11-22: none of them is a municipality with a 2018 price, so the harmonisation weights are complete. **Correction 2026-11-22 (staging run):** the 5 gaps of 2018 are in `GemiddeldeWOZWaardeVanWoningen_63`, not in `Koopwoningen_64`; Koopwoningen is complete for all 380 municipalities, see DATA_DICTIONARY 2.3); `GemiddeldeWOZWaardeVanWoningen_63` filled 2010–2026.
- The table also contains income columns (e.g. `ParticuliereHuishoudensExclStudenten_95`, mean disposable income) in year-specific boundaries, filled 2011–2024 — not used (86380NED is better).

Sample:

| Year | AMS population | AMS households | AMS owner-occ. % | UTR population | UTR households |
|---|---|---|---|---|---|
| 2011 | 779 808 | 427 350 | 24.4 | 311 367 | 162 957 |
| 2022 | 882 633 | 484 574 | 29.0 | 361 699 | 183 465 |
| 2023 | 918 117 | 505 705 | 29.0 | 367 947 | 187 640 |
| 2025 | 934 526 | 516 096 | 30.0 | 376 757 | 194 040 |

The jump in Amsterdam between 2022 and 2023 is the Weesp merger — evidence that this table is in year-specific boundaries.

Caveat: `Koopwoningen_64` is rounded to whole percentages in recent years.

## 4. CPI — `86141NED` (verified)

- Title: *Consumentenprijzen; CPI 2025=100, index en mutaties* (86141ENG). Monthly Dec 2009 – Oct 2026, **plus yearly rows `2010JJ00`–`2025JJ00`** (status Definitief).
- Category key for all expenditure: `'T001112  '` (two trailing spaces — a filter without them returns 0 rows).
- Yearly `CPI_1` (2025 = 100): 2011 69.70 · 2015 74.36 · 2020 79.94 · 2021 82.08 · 2022 90.29 · 2023 93.76 · 2024 96.90 · 2025 100.00. `JaarmutatieCPI_5` 2022 = 10.0 %.
- Alternative: `71905ned` (CPI 1900=100, yearly 1900–2025; keys `CPI_1`, `JaarmutatieCPI_2`) if a longer series or a stable base is needed.
- Use the same deflator for prices and incomes so that real growth rates stay comparable; the PTI ratio itself is unaffected by deflation.

## 5. Municipal reorganisations (verified)

**Source:** `70739ned` *Gebieden; overzicht vanaf 1830* (status up to 01-01-2026). Data columns give only `Begindatum_1`/`Einddatum_2`; the **successor mapping is in the `Description` field of the `RegioS` dimension** (`/70739ned/RegioS`). Example (GM0870 Werkendam):

```
Opgeheven per 01-01-2019, overgegaan naar:
- Altena (GM1959),
... 10090 hectare met 10929 woningen en 27295 inwoners
```

Renames with a code change use: `Naamswijziging per 01-07-2015,\nnieuwe naam: De Fryske Marren (GM1940)`. Descriptions use `\r\n` line endings.

**Prototype result** (regex parser, run in the research environment, not committed):
- 823 abolished municipalities parsed in total; 117 abolitions since 2011-01-01 (129 rows because of splits) + 3 code-changing renames since 2011 (GM0083 → GM1908, GM1921 → GM1940, GM0241 → GM1945).
- Abolitions by year since 2011: 2011: 17, 2012: 4, 2013: 9, 2014: 6, 2015: 13, 2016: 5, 2017: 3, 2018: 11, 2019: 34, 2021: 4, 2022: 11, 2023: 3.
- Splits since 2011: GM0055 Boarnsterhim (4 receivers), GM0788 Haaren (4), GM0140 Littenseradiel (3), GM1671 Maasdonk (2), GM0051 Skarsterlân (2), GM0053 Winsum (2); GM0424 Muiden lists a 0-inhabitant part to Weesp.
- **All 445 GM codes with prices in 83625NED for 2011–2025 resolve to the 342 codes of 2026.** 298 municipalities are unchanged since 2011; 44 are composed of more than one historical code.
- G4: Rotterdam, Den Haag and Utrecht are unchanged since 2011; Amsterdam absorbed Weesp (2022).
- Grenswijzigingen (small boundary corrections between existing municipalities) are not modelled — they are usually a few hectares/inhabitants.

**2026 reference list:** `86247NED` *Gebieden in Nederland 2026* — 342 municipalities with province (`Code_28`), COROP (`Code_10`), landsdeel (`Code_26`), size class (`Code_52`), urbanity class (`Code_54`, 1 = very strongly urban) and population (`Inwonertal_56`). G4 are all in urbanity class 1. Keys in this table are padded (`'GM0363    '`).

**Upcoming change:** `86438NED` *Gebieden in Nederland 2027* has 341 municipalities — GM1696 Wijdemeren is absent. Its successor is not yet in `70739ned` (status 01-01-2026). Not relevant while income is published in the 2026 division.

**Proposed approach** — see `DATA_DICTIONARY.md` section 4: map historical codes → 2026 codes, sum additive variables, and compute a harmonised average price weighted by owner-occupied dwelling stock (`Woningvoorraad_59 * Koopwoningen_64 / 100`), because CBS publishes no transaction counts per municipality.

Harmonised Amsterdam (incl. Weesp), prototype, euro: 2019 481 422 · 2020 507 388 · 2021 564 658 · 2022 617 736 (vs. Amsterdam-only 484 995 · 510 919 · 569 890 · 620 954).

Other CBS options documented (on `www.cbs.nl`, not reachable, not verified): "Gemeenten en COROP vanaf 1981" (xlsx with disappearing code → new code), "Overzicht van alle gebieden" (zip), the "Gemeentelijke indelingen per jaar" pages and the "Hulpbestanden tijdreeksen" page. These could replace the text parser if the owner prefers a static file.

## 6. Municipality boundaries for maps (documented, not verified)

- PDOK OGC API Features, CBS Gebiedsindelingen 2016–present: collection `gemeente_gegeneraliseerd`
  - items: `https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1/collections/gemeente_gegeneraliseerd/items?f=json` (GeoJSON; also `f=jsonfg`)
  - queryable: `jaarcode` (integer) → use `&jaarcode=2026`
  - CRS: CRS84 (default), EPSG:28992 (RD New, storage), EPSG:3857, EPSG:4258
- 1995–2015: `https://api.pdok.nl/cbs/gebiedsindelingen-historisch/ogc/v1/collections/gemeente_gegeneraliseerd`
- Review 2026-11-22: property names verified via `/collections/gemeente_gegeneraliseerd/schema?f=json`: `statcode`, `statnaam`, `jaarcode`, `jrstatcode`, `rubriek`, `startdatum`, `einddatum`. Join on `statcode`. Licence still to be confirmed.
- Power BI note: Shape Map / Azure Maps need TopoJSON or GeoJSON; convert and simplify locally (e.g. mapshaper) and join on the GM code.

## 7. Mortgage interest rates (documented, not verified)

- DNB "Hypotheekrentes banken" dashboard: bank interest rates on new residential mortgages by rate-fixation period, rate on outstanding stock, and new mortgage volume — `https://www.dnb.nl/statistieken/dashboards/woninghypotheken/hypotheekrentes-banken/` (EN: `https://www.dnb.nl/en/statistics/dashboards/residential-mortgages/bank-mortgage-lending-rates/`).
- The dashboard page does not list a table ID, frequency or download URL. DNB's "Data zoeken" / API services should hold the underlying series — **series ID not verified**.
- Alternative to check later: ECB MFI interest rate statistics (MIR) for the Netherlands — series key not verified.

## 8. Rejected candidates

| Candidate | Why rejected |
|---|---|
| `86161NED`, `86004NED`, … (income, indeling 2025/2024/…) | Superseded by `86380NED` (newer boundaries, 2025 added, revised 2024). |
| Kerncijfers wijken en buurten (`85984NED` 2024, `83220NED` 2015, …) | One table per year; column keys change between years (e.g. `GemiddeldInkomenPerInwoner_66` in 2015 vs `_78` in 2024); income per person/recipient rather than household median; boundaries of each year. Good for neighbourhood detail, poor for a time series. |
| Income columns in `70072ned` | Year-specific boundaries and mean (not median) only; 2024 values are preliminary vintage. |
| `85792NED` price index | Not rejected as a validation source: quality-adjusted, only 21 regions (NL, LD, PV, G4), has yearly rows and transaction counts. **Enabled** by D-015. |
| Mean WOZ value (`70072ned`, `85036NED`) | Tax valuation with a 1-year lag (valuation date 1 January of the prior year), not a market price. Possible robustness check. |
| `03759ned` population | Verified to exist (keys `BevolkingOp1Januari_1`, `GemiddeldeBevolking_2`; dimensions Geslacht, Leeftijd, BurgerlijkeStaat, RegioS) but more complex; `70072ned` gives population and households together. |
| `71486ned` households | Valid (`TotaalParticuliereHuishoudens_1`, 2000–2026), but `70072ned` already covers households; keep as fallback. |
| `85927NED` income account by region | National accounts, not available for municipalities. |

## 9. Indicative first result (prototype, for sanity check only)

Price-to-income = harmonised average price / median disposable household income (all households excl. students):

| Year | Amsterdam | Utrecht | Den Haag | Rotterdam | Netherlands |
|---|---|---|---|---|---|
| 2011 | 11.06 | 8.70 | 8.30 | 7.70 | 7.48 |
| 2013 | 9.78 | 7.72 | 7.86 | 6.84 | 6.63 |
| 2019 | 15.14 | 10.55 | 9.93 | 9.31 | 8.19 |
| 2022 | 16.74 | 12.08 | 12.21 | 11.34 | 10.04 |
| 2023 | 14.38 | 10.54 | 10.37 | 10.12 | 9.11 |
| 2025* | 14.43 | 11.09 | 10.48 | 9.78 | 9.46 |

Median municipal PTI: 6.92 (2011) → 8.37 (2024). Highest 2024: GM0417 Laren 17.3, GM0376 Blaricum 15.7, GM0377 Bloemendaal 15.2, GM0096 Vlieland 15.2 (low reliability), GM0629 Wassenaar 14.9.
These numbers are from a quick prototype and must be re-computed by the pipeline.

## 10. Open questions for the owner

1. **Income measure:** confirm median disposable household income, excl. students, as the primary denominator (vs. standardised income or owner-occupier income).
2. **Randstad definition:** G4 only (as in the brief), or also the provinces Noord-Holland, Zuid-Holland and Utrecht (and Almere/Flevoland)?
3. **Time window:** 2011–2025 with 2025 flagged preliminary — or stop at 2024 (all final)?
4. **Harmonisation weight:** owner-occupied dwelling stock (proposed) vs. total dwellings vs. households.
5. **Small municipalities:** exclude or only flag (< 5 000 households, Wadden islands) in rankings?
6. **Mortgage rates (optional Q4):** keep in scope? If yes, the DNB series must be identified manually (site not reachable from this environment).
7. **Map source:** OK to download PDOK GeoJSON locally (jaarcode 2026) and commit a simplified file to the repo?
8. **Mean price caveat:** add the quality-adjusted index (85792NED) as a side check for the G4/provinces?
