# Power BI

The dashboard is a **Power BI Project** (PBIP), not a single `.pbix` file (D-039):

```
powerbi/
├── nl_housing_affordability.pbip              # open this file in Power BI Desktop
├── nl_housing_affordability.SemanticModel/    # the model as TMDL text: tables, relationships, DAX measures
│   └── definition/
│       ├── expressions.tmdl                   # parameter MartsFolder (where the Parquet files are)
│       ├── relationships.tmdl                 # 4 single-direction many-to-one relationships
│       └── tables/
│           ├── fct_*.tmdl, dim_*.tmdl         # generated from the Parquet files (nl_housing.powerbi scaffold)
│           ├── Income basis.tmdl              # the income-basis switch (D-038)
│           └── _Measures.tmdl                 # all DAX measures, in display folders
├── nl_housing_affordability.Report/           # the report (PBIR): six empty pages, visuals are built in Desktop
└── CHECKS.md                                  # control values for every key measure (generated, see below)
```

Why PBIP: every measure, relationship and column format is a line in a text file, so a change to the model is
reviewed in a pull request like the SQL, and `make check-powerbi` tests it in CI without Power BI.

## Status

| Part | State |
|---|---|
| Semantic model (tables, relationships, 50 measures, income-basis switch) | generated, checked offline (`make check-powerbi`); **not yet opened in Power BI** |
| Report pages | created empty: Overview, Map, G4 vs regions, Municipality detail, Municipality tooltip (hidden), Model checks |
| Visuals | to build in Power BI Desktop (owner), layout below |
| Map | needs `make setup-geo && make geo` on the Mac first (PDOK is not reachable from the agent environment) |

What was checked without Power BI: every JSON file of the project validates against Microsoft's published schemas
(`.pbip`, `definition.pbism`, `definition.pbir`, `.platform`, `report.json`, `version.json`, `pages.json`,
`page.json`); `make check-powerbi` confirms every mart column is in the model with the right type and that every
DAX reference points to an existing table, column or measure. What was **not** checked: that Power BI Desktop
loads the TMDL without a parse error, and that the DAX returns the right numbers. Step 4 below does both.

## 1. Open the project (Windows VM, once)

1. On the Mac: `make build` (writes `data/processed/marts/*.parquet` and runs `make check-powerbi`).
2. Share the repo folder with the VM. With Parallels' default *Share Mac → Home folder*, the Mac's
   `~/Documents/nl house affordability` is `\\Mac\Home\Documents\nl house affordability` in Windows; that is the
   default of the parameter. With another set-up (UTM, a mapped drive), note the Windows path of
   `data\processed\marts`.
3. Power BI Desktop (a 2026 release; PBIR is the default report format since spring 2026): *File → Open →
   Browse* and choose `powerbi\nl_housing_affordability.pbip`.
4. If the path differs: *Home → Transform data → Edit parameters → MartsFolder* (folder only, without a file
   name; a trailing `\` does not matter), then *Close & Apply*.
5. *Home → Refresh*. Five tables load from Parquet; `Income basis` and `_Measures` are calculated in the model.
6. *File → Save*. Desktop rewrites the TMDL files in its own layout (annotations, property order). Commit that
   diff in a separate commit ("Power BI Desktop: first save") so later reviews show only real changes.

If Desktop reports a TMDL error on open, it names the file and line: copy the message into the PR, do not edit
around it in Desktop.

## 2. Model

Star schema, Import mode, single-direction filters (one side → many side):

```
dim_province ──< dim_municipality ──< fct_affordability >── dim_year ──< fct_group_affordability

Income basis   (disconnected: read by the measures, no relationship)
_Measures      (measures only)
```

- `fct_affordability`: grain municipality × year (5 130 rows). `fct_group_affordability`: group × year (270 rows),
  the only place where group values (NL, provinces, G4, Rest of NL …) are correct (D-016). It has no relationship
  to the municipality dimension, so **every visual on it needs a filter on `group_type`**.
- Keys and sort helpers are hidden; `year_label` sorts by `year`, `region_group_3` by `region_group_3_sort`,
  `group_name` by `group_name_sort`.
- Implicit measures are switched off (`discourageImplicitMeasures`): every number in a visual is a measure from
  `_Measures`, so nobody can accidentally *sum* a ratio.
- Power Query does nothing but read each Parquet file (`Parquet.Document(File.Contents(...))`); all
  transformation is in SQL. The only parameter is `MartsFolder`.

### How the measures work

Three rules make every measure safe in any visual:

1. **Ratios are never aggregated.** `PTI`, `PTI rank` etc. return a value only when the filter context is exactly
   one fact row (one municipality × one year, or one group × one year); otherwise they are blank. A province total
   therefore comes from `fct_group_affordability`, never from averaging municipal ratios.
2. **One report year.** `Report year` = the latest filtered year (slicer, chart axis); with no year filter it is
   the latest year with final income (`dim_year[is_latest_final_year]`, D-030). Cards therefore show the headline
   year (2024) by default, and a line chart still shows every year.
3. **One switch for the income basis.** `Income basis key` reads the single-select slicer on `'Income basis'`
   (no selection = all households). Every PTI, income, rank and growth measure branches on it; the measures with
   *(all households)* / *(owner-occupiers)* in the name ignore the slicer and are for side-by-side comparisons.

Display folders in `_Measures`: `0 Context` (years, basis, subtitles), `1 Municipality`, `2 Rank`, `3 Group`,
`4 Headline` (fixed groups for cards), `9 Checks`. Every measure has a description (hover in the Data pane).

## 3. Pages to build

General: put a single-select slicer on `'Income basis'[Income basis]` on every page (sync slicers); set each PTI
visual's **subtitle** to *fx → Field value → `PTI subtitle`* (D-038: definition + active basis + year in every
subtitle); a text box with `Preliminary note`; footer "Source: CBS StatLine (83625NED, 86380NED, 85792NED,
86141NED, 86247NED, 70072ned)". Titles say "Price-to-income ratio (×)", never "years of income".

**Overview** (Q1, Q3)
- Cards: `PTI Netherlands`, `PTI change Netherlands`, `PTI G4`, `PTI Rest of NL`, `G4 ÷ Rest of NL`,
  `Share of municipalities where prices outgrew incomes`.
- Context cards (D-038): `Owner-occupier share G4`, `Owner-occupier share Rest of NL`.
- Line chart: X = `dim_year[year_label]`, Y = `Group PTI`, legend = `fct_group_affordability[group_name]`,
  visual filter `group_type = region_group_3` plus `nl`. The 2025* point is preliminary: mark it (dashed line or
  annotation).
- Year slicer (`dim_year[year_label]`, single select, empty by default).

**Map** (Q1, Q2): after `make geo`. Shape map (custom map `data/reference/municipalities_2026.topojson`, key
`statcode`) or Azure Maps reference layer (`.geojson`); Location = `dim_municipality[municipality_code]`, colour =
`PTI` (sequential, one hue). Tooltip page = *Municipality tooltip*. Check that all 342 codes match a shape. Put
the CC BY 4.0 attribution text from the *Map* section below on the page.

**G4 vs regions** (Q3)
- Two cards side by side, independent of the slicer: `G4 ÷ Rest of NL (all households)` and
  `G4 ÷ Rest of NL (owner-occupiers)` (D-038 requirement 3).
- Line chart: X = `year_label`, Y = `G4 ÷ Rest of NL (all households)` and `G4 ÷ Rest of NL (owner-occupiers)`.
- Line chart: `Group price index (base = 100)` and `Group income index (base = 100)` for G4 vs Rest of NL
  (small multiples by `group_name`, filter `group_type = region_group`).
- Table: `group_name` × `Group price growth since base year`, `Group income growth since base year`,
  `Group growth gap (pp)`, `Group real price growth since base year`.

**Municipality detail** (Q2)
- Table: `municipality_name`, `province_name`, `region_group_3`, `PTI`, `PTI rank label`,
  `PTI rank change since base year`, `Price growth since base year`, `Income growth since base year`,
  `Growth gap (pp)`, `Owner-occupier share`; sorted by `PTI rank`. Slicers: province, `region_group_3`, municipality
  search.
- Line chart for the selected municipality: `PTI (all households)` and `PTI (owner-occupiers)` over `year_label`.

**Municipality tooltip** (hidden, 320 × 240, *Page information → Allow use as tooltip*): `municipality_name`,
`PTI`, `PTI rank (all households)`, `PTI rank (owner-occupiers)` (D-038 requirement 4), `Owner-occupier share`.

**Model checks** (keep it in the file, hide it before publishing): cards `Check row counts`, `Check orphan keys`
and a table with the measures of [CHECKS.md](CHECKS.md).

## 4. Verify (before the first commit of visuals)

Open `CHECKS.md` and compare every value on the *Model checks* page. The values there are computed by
`python -m nl_housing.powerbi expected` **in SQL, independently of the DAX**, with the same definitions; it also
runs in the CI pipeline job, which fails when fresh CBS data changes them. A mismatch means a wrong measure,
filter or relationship. Then flip the income-basis slicer and check the *Owner-occupiers* column.

## 5. After changing the marts

```bash
make build                                       # includes check-powerbi
.venv/bin/python -m nl_housing.powerbi expected  # refresh CHECKS.md if numbers changed
```

A new mart column fails `check-powerbi` until it is in the model: add it in Power BI (or re-scaffold that table
with `python -m nl_housing.powerbi scaffold --force` and re-apply Desktop's changes from the git diff).

## Map

Municipality boundaries come from the PDOK OGC API (dataset *CBS Gebiedsindelingen 2016 t/m heden*,
collection `gemeente_gegeneraliseerd`, `jaarcode=2026`), generated by `src/nl_housing/geo.py`
(decision D-014). PDOK is not reachable from the agent environment, so the files are generated
on the owner's Mac.

### Generate the files (macOS, from the repo root)

```bash
.venv/bin/pip install -r requirements-geo.txt     # shapely, pyproj, topojson (arm64 wheels)
.venv/bin/python -m nl_housing.geo --year 2026    # download, validate, simplify, write
```

- The full download is cached in `data/raw/geo/` (gitignored); re-runs reuse it (`--force` re-downloads).
- The script picks the smallest simplification tolerance (in metres) that keeps both files under
  2 MB, and fails if simplification would create gaps or overlaps between neighbours.
  `--tolerance 50` forces a fixed value.
- Output in `data/reference/` (committed): `municipalities_2026.geojson`,
  `municipalities_2026.topojson` and `municipalities_2026.metadata.json` (source query,
  download time, tolerance, file sizes, licence).

### Which file for which visual

| Visual | File | Key |
|---|---|---|
| Shape map (custom map) | `municipalities_2026.topojson` (smaller: shared borders stored once) | map key `statcode` |
| Azure Maps → Reference layer (data-bound) | `municipalities_2026.geojson` | property `statcode` |

Both files hold only two properties: `statcode` (e.g. `GM0363`) and `statnaam`.
Coordinates are WGS84 longitude/latitude. 342 shapes are well inside the documented limits of
both visuals (Shape map: up to 1,500 data points, <https://learn.microsoft.com/en-us/power-bi/visuals/desktop-shape-map>;
Azure Maps reference layer: first 30,000 features,
<https://learn.microsoft.com/en-us/azure/azure-maps/power-bi-visual-add-reference-layer>).

### Join on municipality code

Put the municipality code column of `dim_municipality` (the 2026 GM code, same format as
`statcode`) in the **Location** field, never the municipality name: names are not unique over time and are spelled
differently across sources ('s-Gravenhage / Den Haag). Check after loading: every one of the 342
codes in `dim_municipality` should match a shape (Shape map: *View map type key*).

### Attribution (required by the licence)

The boundary data is licensed under **CC BY 4.0**
(<https://creativecommons.org/licenses/by/4.0/>), as stated on the PDOK API landing page
(<https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1>). Put this text on the map page of the
dashboard and in the main README:

> Municipal boundaries: CBS Gebiedsindelingen (Statistics Netherlands, via PDOK), licensed under
> CC BY 4.0; simplified for this project.

## Income basis (required on every PTI visual, D-038)

The all-household PTI compares prices with what **residents** earn (renters included), not with what **buyers**
earn. With owner-occupier income the G4 gap shrinks sharply and one claim reverses (current numbers: table
"Headline by income basis" in `docs/KEY_FINDINGS.md`, generated by the notebook). Owner decisions of 2026-11-28:
default basis **All households**, with a switch; owner-occupier group income moved into `fct_group_affordability`.

| Requirement | Where it is implemented |
|---|---|
| 1. Label the metric precisely ("Price-to-income ratio (×)", subtitle with the definition; never "years of income") | measure `PTI subtitle`, used as dynamic subtitle |
| 2. Income-basis switch driving every PTI measure, rank and the map; active basis in each subtitle | table `Income basis` + `Income basis key`; all PTI / income / rank / growth measures; `PTI subtitle` |
| 3. G4 ÷ rest under both bases side by side | `G4 ÷ Rest of NL (all households)`, `G4 ÷ Rest of NL (owner-occupiers)` |
| 4. Both ranks in the municipality tooltip | `PTI rank (all households)`, `PTI rank (owner-occupiers)` |
| 5. Context card: owner-occupier share per group | `Owner-occupier share G4`, `Owner-occupier share Rest of NL` (`fct_group_affordability.owner_households_count`) |

The switch is a disconnected table read by the measures, not a field parameter (D-039): a field parameter swaps
the field in a visual, but cannot change the measures that other measures, ranks, conditional formatting (map
colours) and subtitles are built on.
