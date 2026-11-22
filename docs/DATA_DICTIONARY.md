# Data Dictionary

Status: **approved 2026-11-22** (see `DECISIONS_LOG.md`; changes from the research draft are listed in `reviews/2026-11-22_research_review.md`).
All table IDs, column keys, units and dimension codes below were verified against the CBS OData API on 2026-11-14.
Evidence and rejected alternatives are in [`cbs_tables_research.md`](cbs_tables_research.md); decisions are in [`DECISIONS_LOG.md`](DECISIONS_LOG.md).
The machine-readable version is [`config/cbs_tables.yaml`](../config/cbs_tables.yaml).

## 1. Conventions

| Item | Convention |
|---|---|
| Region codes | `NL01` (Netherlands), `LD01`–`LD04` (landsdelen), `PV20`–`PV31` (provinces), `CRxx` (COROP), `GMxxxx` (municipality, 4 digits). |
| Key padding | Some dimension keys are right-padded with spaces (e.g. `'T001112  '`, `'CR04  '`, `'GM0363    '` in 86247NED). **Strip all keys** after loading. |
| Period keys | `YYYYJJ00` = calendar year; `YYYYMMnn` = month; `YYYYKWnn` = quarter. Convert to integer `year`. |
| Missing values | `null` in OData = CBS symbol `.` (unknown, unreliable or confidential). |
| Units | CBS income columns are in **1 000 euro** and household counts in **x 1 000** — convert to euro and absolute counts in the staging layer. |
| Target geography | Municipal division of **1 January 2026** (342 municipalities). Older codes are mapped to it (section 4). |
| Analysis window | **2011–2025** (income starts in 2011; 2025 income is preliminary). |

## 2. Source tables

### 2.1 `83625NED` — house prices

- **NL title:** Bestaande koopwoningen; gemiddelde verkoopprijzen, regio
- **EN title (official):** Existing own homes; average purchase prices, region
- **Coverage:** 1995–2025, yearly (2025 added on 2026-02-17). Figures are final at first publication.
- **Regions:** NL01, LD, PV, GM. The table has 728 GM codes in total; each year is given in **that year's municipal boundaries** (e.g. 418 municipalities in 2011, 342 in 2023–2025).
- **Source:** Kadaster notary transactions, purchases by private persons.

| Column key | Title (NL) | Description (EN) | Unit |
|---|---|---|---|
| `RegioS` | Regio's | Region code | code |
| `Perioden` | Perioden | Year | `YYYYJJ00` |
| `GemiddeldeVerkoopprijs_1` | Gemiddelde verkoopprijs | Average sale price of existing owner-occupied homes | euro |

### 2.2 `86380NED` — household income

- **NL title:** Inkomen van huishoudens; huishoudenskenmerken, regio (indeling 2026)
- **EN title (translation):** Income of households; household characteristics, region (2026 municipal division)
- **Coverage:** 2011–2025, yearly. 2011–2024 final ("Definitief"); 2025 preliminary ("Voorlopig").
- **Regions:** NL01, 4 LD, 12 PV, 40 CR, 35 AM (labour-market regions), **342 GM — all years in the 1 January 2026 boundaries**.
- **Population:** private households with known income, measured on 1 January of the reporting year.

Dimensions used:

| Dimension | Key | Meaning |
|---|---|---|
| `Populatie` | `3000870` | Private households **excl.** student households (**proposed default**) |
| `Populatie` | `1050010` | Private households incl. student households |
| `KenmerkenVanHuishoudens` | `1050010` | All private households (**proposed default**) |
| `KenmerkenVanHuishoudens` | `1014800` | Owner-occupier households ("Woningbezit: eigen woning") |
| `KenmerkenVanHuishoudens` | `1014850` | Tenant households ("Woningbezit: huurwoning") — available, not loaded |

Columns:

| Column key | Title (NL) | Description (EN) | Unit |
|---|---|---|---|
| `ParticuliereHuishoudens_1` | Particuliere huishoudens | Number of private households | x 1 000 |
| `GemiddeldGestandaardiseerdInkomen_3` | Gemiddeld gestandaardiseerd inkomen | Mean standardised (equivalised) income | 1 000 euro |
| `MediaanGestandaardiseerdInkomen_4` | Mediaan gestandaardiseerd inkomen | Median standardised (equivalised) income | 1 000 euro |
| `GemiddeldBesteedbaarInkomen_5` | Gemiddeld besteedbaar inkomen | Mean disposable household income | 1 000 euro |
| `MediaanBesteedbaarInkomen_6` | Mediaan besteedbaar inkomen | **Median disposable household income** | 1 000 euro |

Definitions (from the table metadata, translated):
- *Disposable income* = gross income minus income transfers paid, income-insurance premiums, health-insurance premiums and taxes on income and wealth.
- *Standardised income* = disposable income corrected for household size and composition with equivalence factors; a welfare measure for household members, comparable across household types.

### 2.3 `70072ned` — population, households, housing stock

- **NL title:** Regionale kerncijfers Nederland
- **EN title (translation):** Regional key figures Netherlands
- **Coverage:** 1995–2026 yearly; columns are not filled for every year (see below).
- **Regions:** NL01, LD, PV, CR, GM (728 GM codes in total). Each year uses **that year's municipal boundaries**.

| Column key | Title (NL) | Description (EN) | Unit | Filled (GM level) |
|---|---|---|---|---|
| `TotaleBevolking_1` | Totale bevolking | Population on 1 January | count | 2010–2026 |
| `TotaalParticuliereHuishoudens_51` | Totaal particuliere huishoudens | Private households | count | 2010–2025 |
| `GemiddeldeHuishoudensgrootte_58` | Gemiddelde huishoudensgrootte | Average household size | persons | 2010–2025 |
| `Woningvoorraad_59` | Woningvoorraad | Dwelling stock | count | 2010–2025 |
| `Koopwoningen_64` | Koopwoningen | Share of owner-occupied dwellings | % | 2010–2025 |
| `GemiddeldeWOZWaardeVanWoningen_63` | Gemiddelde WOZ-waarde van woningen | Mean WOZ (municipal tax) value of dwellings | 1 000 euro | 2010–2026 (5 gaps in 2018: GM0417, GM0743, GM0847, GM1702, GM1721)¹ |

¹ Corrected 2026-11-22 from the staging run (`staging.stg_cbs__regional_key_figures`): the five 2018 gaps are in the WOZ value, not in `Koopwoningen_64`, which is complete for all 380 municipalities of 2018. The harmonisation weight (D-007/D-011) is therefore unaffected; WOZ for these five is missing.

### 2.4 `86141NED` — consumer price index

- **NL title:** Consumentenprijzen; CPI 2025=100, index en mutaties
- **EN title (official, 86141ENG):** Consumer prices; CPI 2025=100, index and rates of change
- **Coverage:** monthly Dec 2009 – Oct 2026, plus yearly averages `2010JJ00`–`2025JJ00` (final).
- **Filter:** `Bestedingscategorieen eq 'T001112  '` (= "000000 Alle bestedingen", all expenditure; note the two trailing spaces).

| Column key | Title (NL) | Description (EN) | Unit |
|---|---|---|---|
| `CPI_1` | CPI | Consumer price index | 2025 = 100 |
| `JaarmutatieCPI_5` | Jaarmutatie CPI | Year-on-year change | % |

### 2.5 `86247NED` — municipality reference (2026 division)

- **NL title:** Gebieden in Nederland 2026 — **EN (translation):** Regions in the Netherlands 2026
- 342 municipalities; one row per municipality.

| Column key | Description (EN) |
|---|---|
| `Code_1`, `Naam_2` | Municipality code and name |
| `Code_10`, `Naam_11` | COROP region |
| `Code_26`, `Naam_27` | Landsdeel |
| `Code_28`, `Naam_29` | Province (`PVxx`) |
| `Code_52`, `Omschrijving_53` | Municipality size class |
| `Code_54`, `Omschrijving_55` | Urbanity class (1 = very strongly urban … 5 = not urban) |
| `Inwonertal_56` | Population |

### 2.6 `70739ned` — municipal reorganisations

- **NL title:** Gebieden; overzicht vanaf 1830 — **EN (translation):** Regions; overview since 1830
- Data columns: `Begindatum_1`, `Einddatum_2` (start/end date), `GebiedsOfGemeentecode_3`, `Provincie_4`.
- **The successor information is in the `Description` text of the `RegioS` dimension** (`/70739ned/RegioS`), see section 4.

## 3. Metric definitions (approved 2026-11-22)

All amounts in euro after unit conversion. `y` = year, `m` = municipality (2026 code). Column names follow D-017.

| Column | Definition | Notes |
|---|---|---|
| `avg_sale_price_eur` | `GemiddeldeVerkoopprijs_1`, harmonised to 2026 boundaries (section 4) | Mean price of transacted homes, not quality-adjusted. |
| `median_disposable_income_eur` | `MediaanBesteedbaarInkomen_6 * 1000`, Populatie `3000870`, Kenmerk `1050010` | **Primary income measure** (D-003). |
| `median_disposable_income_owner_eur` | same, Kenmerk `1014800` | **Mandatory sensitivity**: income of current owner-occupiers. |
| **`price_to_income_ratio`** (PTI) | `avg_sale_price_eur / median_disposable_income_eur` | **Primary affordability metric.** "Years of median household disposable income needed to buy the average home." Higher = less affordable. Level is inflated by the mean/median mix — compare changes and ranks (D-004). |
| `price_to_income_owner_ratio` | `avg_sale_price_eur / median_disposable_income_owner_eur` | Less sensitive to the share of renters, singles and students. |
| `cpi_2025` | `CPI_1` (yearly average, 2025 = 100) | |
| `real_avg_sale_price_eur_2025` | `avg_sale_price_eur * 100 / cpi_2025` | In 2025 euro. |
| `real_median_disposable_income_eur_2025` | `median_disposable_income_eur * 100 / cpi_2025` | In 2025 euro. |
| `price_growth_since_2011_pct`, `income_growth_since_2011_pct` | `(x_y / x_2011 - 1) * 100`, nominal and real variants | Base year 2011 = first year with income (D-008). |
| `growth_gap_pp` | `price_growth_since_2011_pct - income_growth_since_2011_pct` | Where prices outpaced incomes (Q3). |
| `pti_rank_desc` | rank of `price_to_income_ratio` within year, 1 = least affordable, among rows without `low_reliability` / `income_missing` | Ranking shifts (Q2); flagged rows get `null` (D-009). |
| `region_group` | `G4` if `m` in {GM0363, GM0599, GM0518, GM0344}; otherwise `Rest of NL` | Primary split (D-010). |
| `region_group_3` | `G4` / `Rest of Randstad provinces` (PV26, PV27, PV28 excl. G4) / `Rest of NL` | Secondary split (D-010). |
| `urbanity_class` | `86247NED` `Code_54` (1 = very strongly urban … 5 = not urban) | "Randstad vs big-city effect" lens. |

### Group aggregates (D-016)

| Group | Price | Median income |
|---|---|---|
| Province, NL | CBS row `PVxx` / `NL01` in `83625NED` | CBS row `PVxx` / `NL01` in `86380NED` |
| Single G4 city | municipality row | municipality row |
| G4 combined | transaction-weighted (`85792NED.VerkochteWoningen_4`) | household-weighted mean of medians *(approx.)* |
| Rest of NL | `(p_NL * n_NL - sum_g p_g * n_g) / (n_NL - sum_g n_g)` — exact | household-weighted mean of medians *(approx.)* |
| Rest of Randstad provinces | owner-stock-weighted mean *(approx.)* | household-weighted mean of medians *(approx.)* |

Never average municipal ratios unweighted for a headline figure. Validation: the household-weighted mean of medians over all 342 municipalities must stay within 2 % of the official NL median for every year (2011: +0.57 %, 2024: +0.80 %).

### Q4 scenario metrics (D-013)

Parameters live in one config file (planned: `config/scenarios.yaml`) and are printed on the dashboard.

| Column | Definition |
|---|---|
| `monthly_payment_eur` | annuity `L * r / (1 - (1 + r)^-n)`, `L = avg_sale_price_eur` (100 % LTV), `r = rate / 12`, `n = 360`; computed for each rate of the scenario grid |
| `payment_to_income_pct` | `100 * 12 * monthly_payment_eur / median_disposable_income_eur` (gross of mortgage-interest tax relief — stated as a limitation) |
| `upfront_cost_saving_years` | `upfront_cost_share * avg_sale_price_eur / (savings_rate * median_disposable_income_eur)` |

### Data-quality flags

| Flag | Rule |
|---|---|
| `is_preliminary` | CBS `Perioden.Status = 'Voorlopig'` in `86380NED` (currently 2025). Never hard-code the year. |
| `is_harmonised` | Municipality value built from more than one historical code in that year. |
| `low_reliability` | Fewer than 5 000 households (`ParticuliereHuishoudens_1 < 5`); 19 municipalities in 2024. |
| `income_missing` | Income suppressed (`null`); in 2025: GM0088 Schiermonnikoog, GM0096 Vlieland, GM0277 Rozendaal. |

## 4. Harmonisation to 2026 boundaries (approved, D-007)

1. Parse `70739ned/RegioS` → `Description` into a mapping `old_code → new_code` with the number of inhabitants (and dwellings) transferred. Two patterns:
   - `Opgeheven per DD-MM-YYYY, overgegaan naar: - <name> (GMxxxx), ... <ha> hectare met <n> woningen en <n> inwoners` (abolished; 1 line per receiving municipality),
   - `Naamswijziging per DD-MM-YYYY, nieuwe naam: <name> (GMxxxx)` (rename with a new code, e.g. GM1921 → GM1940, GM0241 → GM1945).
2. Resolve chains recursively until the code is in the 2026 list. For splits (6 real splits since 2011, e.g. GM0788 Haaren → 4 municipalities; GM0424 Muiden also lists a 0-inhabitant part), use the inhabitant shares as allocation weights; drop rows with weight 0.
3. **Additive variables** (population, households, dwellings): `value_2026 = sum(value_old * weight)`.
4. **Average price**: weighted mean of historical averages with weight = `owner_occupied_stock_old * weight`, where `owner_occupied_stock = Woningvoorraad_59 * Koopwoningen_64 / 100` from `70072ned` (CBS publishes no transaction counts per municipality).
5. **Income** needs no harmonisation (86380NED is already in 2026 boundaries).
6. Prototype result (research, not yet reproducible): all 445 historical GM codes that appear in 83625NED for 2011–2025 resolve to the 2026 list. Must be reproduced by committed, tested code; the resulting mapping is committed as `data/reference/municipality_mapping_2026.csv`.
7. Edge case 2015: De Fryske Marren appears twice (GM1921 old name, GM1940 new name from 01-07-2015); both map to GM1940 with equal weight (no transaction counts).
