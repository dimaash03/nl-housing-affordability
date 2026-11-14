# Data Dictionary

Status: **draft — proposed, needs owner approval.**
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
| `Koopwoningen_64` | Koopwoningen | Share of owner-occupied dwellings | % | 2010–2025 (5 gaps in 2018) |
| `GemiddeldeWOZWaardeVanWoningen_63` | Gemiddelde WOZ-waarde van woningen | Mean WOZ (municipal tax) value of dwellings | 1 000 euro | 2010–2026 |

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

## 3. Metric definitions (proposed)

All amounts in euro after unit conversion. `y` = year, `m` = municipality (2026 code).

| Metric | Definition | Notes |
|---|---|---|
| `avg_price` | `GemiddeldeVerkoopprijs_1`, harmonised to 2026 boundaries | Mean price of transacted homes, not quality-adjusted. |
| `median_disp_income_hh` | `MediaanBesteedbaarInkomen_6 * 1000`, Populatie `3000870`, Kenmerk `1050010` | **Primary income measure.** |
| `median_disp_income_owner_hh` | same, Kenmerk `1014800` | Sensitivity: income of current owner-occupiers. |
| **`price_to_income`** (PTI) | `avg_price / median_disp_income_hh` | **Primary affordability metric.** "Years of median household disposable income needed to buy the average home." Higher = less affordable. |
| `price_to_income_owner` | `avg_price / median_disp_income_owner_hh` | Secondary; less sensitive to the share of renters/students in a municipality. |
| `cpi_2025` | `CPI_1` (yearly average, 2025 = 100) | |
| `real_avg_price` | `avg_price * 100 / cpi_2025` | In 2025 euro. |
| `real_median_income` | `median_disp_income_hh * 100 / cpi_2025` | In 2025 euro. |
| `price_growth_pct`, `income_growth_pct` | `(x_y / x_2011 - 1) * 100`, nominal or real | PTI growth ≈ price growth relative to income growth; CPI cancels out of PTI. |
| `growth_gap_pp` | `price_growth_pct - income_growth_pct` | Where prices outpaced incomes (Q3). |
| `pti_rank` | rank of `price_to_income` within year, 1 = least affordable | For ranking shifts (Q2). |
| `region_group` | `G4` if `m` in {GM0363, GM0599, GM0518, GM0344}; otherwise `Rest of NL` | Optional second split: Randstad provinces (PV26, PV27, PV28) vs rest — **owner to decide**. |
| `pti_group` (aggregate) | `sum(avg_price_m * households_m) / sum(median_income_m * households_m)` | Household-weighted ratio of means for provinces and groups; never average the municipal ratios unweighted. |
| `deposit_years` (optional) | `(deposit_share * avg_price) / (savings_rate * median_disp_income_hh)` | Proposed assumptions: `deposit_share` = 0.10 (≈ purchase costs + small down payment), `savings_rate` = 0.10. Parameters must be configurable. |
| `monthly_payment` (optional) | annuity: `L * r / (1 - (1 + r)^-360)`, `r` = annual DNB rate / 12, `L` = `avg_price` (100 % LTV) | Needs the DNB rate series (not yet sourced). |
| `payment_to_income` (optional) | `12 * monthly_payment / median_disp_income_hh` | |

Data-quality flags (proposed):

| Flag | Rule |
|---|---|
| `is_preliminary` | `year = 2025` (income preliminary). |
| `is_harmonised` | Municipality value was built from more than one historical code (44 of 342 municipalities for at least one year). |
| `low_reliability` | Fewer than 5 000 households (`ParticuliereHuishoudens_1 < 5`) — few transactions, volatile averages (e.g. Wadden islands). |
| `income_missing` | Income suppressed (`null`); in 2025 this affects 3 municipalities for all households (GM0088 Schiermonnikoog, GM0096 Vlieland, GM0277 Rozendaal). |

## 4. Harmonisation to 2026 boundaries (proposed)

1. Parse `70739ned/RegioS` → `Description` into a mapping `old_code → new_code` with the number of inhabitants (and dwellings) transferred. Two patterns:
   - `Opgeheven per DD-MM-YYYY, overgegaan naar: - <name> (GMxxxx), ... <ha> hectare met <n> woningen en <n> inwoners` (abolished; 1 line per receiving municipality),
   - `Naamswijziging per DD-MM-YYYY, nieuwe naam: <name> (GMxxxx)` (rename with a new code, e.g. GM1921 → GM1940, GM0241 → GM1945).
2. Resolve chains recursively until the code is in the 2026 list. For splits (6 real splits since 2011, e.g. GM0788 Haaren → 4 municipalities; GM0424 Muiden also lists a 0-inhabitant part), use the inhabitant shares as allocation weights; drop rows with weight 0.
3. **Additive variables** (population, households, dwellings): `value_2026 = sum(value_old * weight)`.
4. **Average price**: weighted mean of historical averages with weight = `owner_occupied_stock_old * weight`, where `owner_occupied_stock = Woningvoorraad_59 * Koopwoningen_64 / 100` from `70072ned` (CBS publishes no transaction counts per municipality).
5. **Income** needs no harmonisation (86380NED is already in 2026 boundaries).
6. Tested: all 445 historical GM codes that appear in 83625NED for 2011–2025 resolve to the 2026 list.
