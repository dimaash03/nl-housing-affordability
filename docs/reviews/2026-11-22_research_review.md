# Review — research PR #1 and pipeline scaffold (2026-11-22)

Scope: PR #1 (`docs/cbs_tables_research.md`, `docs/DATA_DICTIONARY.md`, `docs/DECISIONS_LOG.md`, `config/cbs_tables.yaml`) and the scaffold on `main` (`src/nl_housing/`, tests, Makefile).
Decisions taken on the open questions are recorded in [`../DECISIONS_LOG.md`](../DECISIONS_LOG.md) (D-003 … D-017).

## 1. Independent checks (re-run against the CBS OData API on 2026-11-22)

| Check | Result |
|---|---|
| `pytest` on `main` and on the PR branch | 31 passed / 31 passed |
| Real config parses | 9 entries, 7 enabled after this review (85792NED enabled) |
| `DataProperties` types of all 7 tables | only `Dimension`, `GeoDimension`, `TimeDimension`, `Topic` — no type without a code-table endpoint, so `ingest.DIMENSION_TYPES` works for every table |
| Table metadata | titles/periods as in the PR; `86141NED` modified 2026-11-10, `85792NED` 2026-10-22 (newer than in the research notes, no impact) |
| Sample prices `83625NED` (AMS / UTR / NL, 2011, 2024, 2025) | identical to the research table |
| Sample income `86380NED` (AMS 2011 25.5, 2024 42.0, 2025 43.7; mean 2024 58.2) | identical |
| `Perioden.Status` `86380NED` | 2023, 2024 `Definitief`; 2025 `Voorlopig` |
| CPI `86141NED` with key `'T001112  '` | 2011 69.70, 2024 96.90 — identical |
| `86247NED` | 342 rows, keys padded (`'GM1680    '`) |
| Population reference date `86380NED` | "1 januari van het verslagjaar" — as stated |
| `85792NED` | yearly rows 1995–2025, 21 regions, `VerkochteWoningen_4` + `GemiddeldeVerkoopprijs_7`; average prices equal `83625NED` for NL and G4 (2024) |
| Small municipalities | 2024: 19 with < 5 000 households, 95 with < 10 000 |
| 2018 owner-occupied share gaps | 0 gaps among the 380 municipalities with a 2018 price |
| Harmonisation weight (reproduce official NL average price) | 2024: owner stock −1.09 %, dwellings −0.54 %, households −0.34 %; 2019: −0.71 %, +0.71 %, +1.02 % |
| Group income aggregation (hh-weighted mean of medians vs official NL median) | 2011 +0.57 %, 2024 +0.80 % |
| PDOK schema | properties `statcode`, `statnaam`, `jaarcode`, … (licence not stated in the schema) |

Verdict: the research is solid — every value I re-checked matches the API. The weaknesses are in method details and reproducibility, not in the sourcing.

## 2. Findings — research PR (fixed in this review unless marked *open*)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| R1 | high | Group aggregation weighted **prices by households** — no conceptual basis | D-016: official CBS rows for PV/NL; exact Rest-of-NL price from `85792NED` transaction counts; validated income aggregation |
| R2 | high | Harmonisation parser not committed → "445 → 342" is not reproducible | D-007: re-implement with tests + committed mapping CSV — *open, assigned to the harmonisation agent* |
| R3 | medium | `deposit_years` with 10 % deposit / 10 % savings rate does not fit the Dutch market (100 % LTV) | D-013: re-framed Q4 (rate grid, upfront costs, stretch: borrowing gap) |
| R4 | medium | `is_preliminary` hard-coded as `year = 2025` | D-008: derive from `Perioden.Status` |
| R5 | medium | Owner-occupier PTI was optional; the all-households median biases Amsterdam | D-003: mandatory sensitivity |
| R6 | low | Metric names without units (`avg_price`, `price_to_income`) violate CLAUDE.md | D-017 naming |
| R7 | low | "5 gaps in 2018" for `Koopwoningen_64` left unresolved | checked: no impact (D-011) |
| R8 | low | `filters`/`endpoint` keys in the config look executable but are not used by `ingest.py` | header comment added |
| R9 | low | PDOK property names marked not verified | verified via schema; licence still *open* (D-014) |

## 3. Findings — scaffold on `main` (*open*, assigned to the pipeline agent)

| # | Severity | Finding | Proposed fix |
|---|---|---|---|
| C1 | medium | No retry/backoff on CBS requests; one transient 5xx fails a whole table | `requests` session with `urllib3.Retry` (429/5xx, backoff), tested offline |
| C2 | medium | No SQL runner yet; `sql/staging` and `sql/marts` cannot be executed | `python -m nl_housing.transform` executing files in dependency order, idempotent (`CREATE OR REPLACE`) |
| C3 | medium | No data tests (row counts, uniqueness of keys, null rates) | `tests/data/` or SQL assertions run after `make transform` |
| C4 | low | Dependencies have only lower bounds — runs are not reproducible | add `requirements.lock` (pip freeze) and mention it in the README |
| C5 | low | No linter config | add `ruff` to dev dependencies + `make lint` |
| C6 | low | README business questions differ from the project brief (Q4 missing) | fixed in this review |
| C7 | info | No Parquet export of marts for Power BI | planned step `make export` |

## 4. What the owner should be able to explain in an interview

- Why the median disposable household income, and why the owner-occupier version is a mandatory check (D-003).
- Why the PTI level is inflated by mean/median, and why the report therefore focuses on changes and ranks (D-004).
- How the herindelingen were handled, and the evidence that the weight choice changes the national average by ~1 % at most (D-007).
- How Rest-of-NL is computed exactly from transaction counts instead of a proxy weight (D-016).
- Why "10 % deposit" is the wrong question in the Netherlands (D-013).
