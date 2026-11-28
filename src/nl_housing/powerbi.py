"""Power BI semantic model as code (PBIP / TMDL): scaffold the mart tables and check the model for drift.

The dashboard is a Power BI Project (``powerbi/nl_housing_affordability.pbip``). Its semantic model is stored as
TMDL text files, so it can be reviewed in a pull request like the SQL (decision D-039). Two kinds of files:

- **Generated** (``scaffold``): one ``tables/<mart>.tmdl`` per mart table, with columns, data types, formats,
  descriptions and the Power Query partition that reads ``data/processed/marts/<mart>.parquet``. Types come from
  the exported Parquet files, i.e. exactly what Power BI will import.
- **Hand-written**: ``_Measures.tmdl`` (DAX), ``Income basis.tmdl`` (switch table), ``relationships.tmdl``,
  ``expressions.tmdl`` (the folder parameter), ``model.tmdl`` and ``database.tmdl``.

Once the owner has opened and saved the project in Power BI Desktop, Desktop rewrites the files (it adds
annotations and may reorder properties). ``scaffold`` therefore never overwrites an existing file unless
``--force`` is given; ``check`` is the ongoing contract. It runs offline, without Power BI, and reports:

- a mart column missing from the model, an extra model column, or a different data type;
- a DAX reference ``table[column]`` to a table or column that does not exist;
- a bare ``[name]`` reference that is neither a measure nor a column created inside the expression (``[@x]``);
- a relationship or sort-by column that does not exist.

It does not evaluate DAX. The values are checked in Power BI against ``powerbi/CHECKS.md``, written by ``expected``:
the same definitions as the DAX measures, computed independently in SQL on the DuckDB marts.

Usage::

    python -m nl_housing.powerbi scaffold [--force]   # after `make export`
    python -m nl_housing.powerbi check                # `make check-powerbi`
    python -m nl_housing.powerbi expected             # write powerbi/CHECKS.md from the built database
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from nl_housing import config, export

logger = logging.getLogger(__name__)

PROJECT_NAME = "nl_housing_affordability"
MART_TABLES = ("dim_municipality", "dim_province", "dim_year", "fct_affordability", "fct_group_affordability")

# Stable lineage tags: the same table/column always gets the same id, so a re-scaffold produces no diff.
_NAMESPACE = uuid.UUID("5c2b6a1e-3f0d-4c9a-9a57-0d3f3c1b7e21")

# DuckDB type of the Parquet column -> TMDL dataType.
_TYPE_MAP = {
    "VARCHAR": "string",
    "BOOLEAN": "boolean",
    "TINYINT": "int64",
    "SMALLINT": "int64",
    "INTEGER": "int64",
    "BIGINT": "int64",
    "FLOAT": "double",
    "DOUBLE": "double",
    "DATE": "dateTime",
}

TABLE_DESCRIPTIONS = {
    "dim_municipality": "The 342 municipalities of 1 Jan 2026 (86247NED): province, COROP, region groups (D-010).",
    "dim_province": "The 12 provinces; is_randstad_province marks Utrecht, Noord-Holland and Zuid-Holland.",
    "dim_year": "Analysis years 2011-2025; year_label has a * for preliminary income (D-030).",
    "fct_affordability": "Municipality (2026 division) x year: price, income, PTI, growth, ranks and flags.",
    "fct_group_affordability": (
        "Group x year (NL, provinces, G4 / Rest of NL, three-way split). Group PTI = group price / group income, "
        "never an average of municipal ratios (D-016). Filter group_type in every visual."
    ),
}

# Keys and sort helpers: used by relationships / sort-by, not dragged into visuals.
HIDDEN_COLUMNS = {
    "fct_affordability": {"municipality_code", "year"},
    "fct_group_affordability": {"year", "group_sort", "group_name_sort"},
    "dim_municipality": {"region_group_3_sort", "g4_sort_order"},
}

SORT_BY = {
    ("dim_year", "year_label"): "year",
    ("dim_municipality", "region_group_3"): "region_group_3_sort",
    ("fct_group_affordability", "group_name"): "group_name_sort",
}

COLUMN_DESCRIPTIONS = {
    "avg_sale_price_eur": "Average sale price of existing homes (83625NED), EUR, in 2026 boundaries (D-007).",
    "median_disposable_income_eur": (
        "Median disposable income of all private households excl. students (86380NED), EUR (D-003)."
    ),
    "median_disposable_income_owner_eur": "Median disposable income of owner-occupier households (86380NED), EUR.",
    "price_to_income_ratio": (
        "Average sale price / median disposable income of all households; a relative index (D-038)."
    ),
    "price_to_income_owner_ratio": "Average sale price / median disposable income of owner-occupier households.",
    "households_count": "Private households (all), the weight of the group income (D-016).",
    "owner_households_count": "Owner-occupier households, the weight of the owner-occupier group income (D-034).",
    "pti_rank_desc": "Rank of the all-household PTI within the year, 1 = least affordable; null if not ranked (D-009).",
    "pti_owner_rank_desc": "Rank of the owner-occupier PTI on the same set of municipalities as pti_rank_desc (D-038).",
    "low_reliability": "Fewer than 5 000 households: PTI shown, but not ranked (D-009).",
    "income_missing": "No income published for this municipality-year.",
    "is_preliminary": "Income is preliminary (CBS period status), currently 2025.",
    "is_harmonised": "Price built from more than one historical municipality (merger, D-026).",
    "is_income_approximated": (
        "Group income is the household-weighted mean of municipal medians, not a published median (D-016)."
    ),
    "group_type": "nl / province / region_group (G4 vs Rest of NL) / region_group_3 (three-way split).",
    "year_label": "Year as text; 2025* = preliminary income.",
    "is_latest_final_year": "Latest year with final income: the default (headline) year of the dashboard.",
}


@dataclass(frozen=True)
class ColumnSpec:
    """One model column of a mart table."""

    name: str
    data_type: str
    format_string: str | None = None
    hidden: bool = False
    sort_by: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class TableSpec:
    """One mart table as a model table."""

    name: str
    columns: tuple[ColumnSpec, ...]
    description: str | None = None


@dataclass
class ParsedModel:
    """What ``check`` needs from the TMDL folder (a light parser, not a full TMDL implementation)."""

    columns: dict[str, dict[str, str | None]] = field(default_factory=dict)  # table -> column -> dataType
    measures: dict[str, str] = field(default_factory=dict)  # measure name -> DAX expression
    sort_by: list[tuple[str, str, str]] = field(default_factory=list)  # (table, column, sort-by column)
    relationships: list[tuple[str, str]] = field(default_factory=list)  # ("table.column", "table.column")


# --- paths -----------------------------------------------------------------------------------------------------


def project_dir(root: Path = config.REPO_ROOT) -> Path:
    """``powerbi/`` folder that holds the ``.pbip`` project."""
    return root / "powerbi"


def definition_dir(root: Path = config.REPO_ROOT) -> Path:
    """TMDL folder of the semantic model."""
    return project_dir(root) / f"{PROJECT_NAME}.SemanticModel" / "definition"


def lineage_tag(*parts: str) -> str:
    """Deterministic lineage tag (UUID) for a model object."""
    return str(uuid.uuid5(_NAMESPACE, ".".join(parts)))


# --- scaffold --------------------------------------------------------------------------------------------------


def format_string(column: str, data_type: str) -> str | None:
    """Display format from the column-name suffix (D-017 units). Years and ranks never get a thousands separator."""
    if data_type not in {"int64", "double"}:
        return None
    if column == "year" or column.endswith(("_sort", "_order", "_desc", "_class", "_code")) or "years_" in column:
        return "0"
    if column.endswith("_eur") or column.endswith("_eur_2025"):
        return "#,0"
    if column.endswith("_ratio"):
        return "0.00"
    if column.endswith(("_pct", "_pp", "_index")):
        return "0.0"
    return "#,0"  # counts, population


def parquet_columns(path: Path) -> list[tuple[str, str]]:
    """(name, DuckDB type) of the columns of an exported Parquet file, in file order."""
    with duckdb.connect() as con:
        rows = con.execute("select column_name, column_type from (describe select * from read_parquet(?))", [str(path)])
        return [(name, ctype) for name, ctype in rows.fetchall()]


def table_spec(table: str, columns: list[tuple[str, str]]) -> TableSpec:
    """Model table for a mart table from its Parquet column types."""
    specs = []
    for name, duck_type in columns:
        if duck_type not in _TYPE_MAP:
            raise ValueError(f"{table}.{name}: no TMDL data type for DuckDB type {duck_type}")
        data_type = _TYPE_MAP[duck_type]
        specs.append(
            ColumnSpec(
                name=name,
                data_type=data_type,
                format_string=format_string(name, data_type),
                hidden=name in HIDDEN_COLUMNS.get(table, set()),
                sort_by=SORT_BY.get((table, name)),
                description=COLUMN_DESCRIPTIONS.get(name),
            )
        )
    return TableSpec(name=table, columns=tuple(specs), description=TABLE_DESCRIPTIONS.get(table))


def _partition_source(table: str) -> list[str]:
    """Power Query of a mart table: read its Parquet file from the MartsFolder parameter, no transformation."""
    return [
        "let",
        '    Folder = Text.TrimEnd(MartsFolder, {"\\", "/"}),',
        f'    Source = Parquet.Document(File.Contents(Folder & "\\{table}.parquet"))',
        "in",
        "    Source",
    ]


def render_table(spec: TableSpec) -> str:
    """TMDL text of one mart table (tabs for indentation, as Power BI Desktop writes it)."""
    t = "\t"
    lines: list[str] = []
    if spec.description:
        lines.append(f"/// {spec.description}")
    lines += [f"table {spec.name}", f"{t}lineageTag: {lineage_tag(spec.name)}", ""]
    for col in spec.columns:
        if col.description:
            lines.append(f"{t}/// {col.description}")
        lines.append(f"{t}column {col.name}")
        lines.append(f"{t * 2}dataType: {col.data_type}")
        if col.hidden:
            lines.append(f"{t * 2}isHidden")
        if col.format_string:
            lines.append(f"{t * 2}formatString: {col.format_string}")
        lines.append(f"{t * 2}lineageTag: {lineage_tag(spec.name, col.name)}")
        lines.append(f"{t * 2}summarizeBy: none")
        lines.append(f"{t * 2}sourceColumn: {col.name}")
        if col.sort_by:
            lines.append(f"{t * 2}sortByColumn: {col.sort_by}")
        lines += ["", f"{t * 2}annotation SummarizationSetBy = User", ""]
    lines.append(f"{t}partition {spec.name} = m")
    lines.append(f"{t * 2}mode: import")
    lines.append(f"{t * 2}source =")
    lines += [f"{t * 4}{line}" for line in _partition_source(spec.name)]
    lines += ["", f"{t}annotation PBI_ResultType = Table", ""]
    return "\n".join(lines)


def scaffold(root: Path = config.REPO_ROOT, force: bool = False) -> list[Path]:
    """Write ``tables/<mart>.tmdl`` for every mart table from its Parquet file; skip existing files unless forced."""
    parquet_dir = export.export_dir(root)
    tables_dir = definition_dir(root) / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for table in MART_TABLES:
        source = parquet_dir / f"{table}.parquet"
        if not source.exists():
            raise FileNotFoundError(f"{source} not found - run `make export` first")
        target = tables_dir / f"{table}.tmdl"
        if target.exists() and not force:
            logger.info("Keep %s (exists; --force to overwrite)", target.relative_to(root))
            continue
        target.write_text(render_table(table_spec(table, parquet_columns(source))), encoding="utf-8")
        logger.info("Wrote %s", target.relative_to(root))
        written.append(target)
    return written


# --- check -----------------------------------------------------------------------------------------------------

_NAME = r"(?:'(?:[^']|'')+'|[^\s=']+)"
_TABLE_RE = re.compile(rf"^table ({_NAME})\s*$")
_COLUMN_RE = re.compile(rf"^\tcolumn ({_NAME})\s*(?:=.*)?$")
_MEASURE_RE = re.compile(rf"^\tmeasure ({_NAME})\s*=\s*(.*)$")
_PROP_RE = re.compile(r"^\t\t(\w+)(?::\s*(.*))?$")
_REL_FROM = re.compile(r"^\tfromColumn:\s*(.+)$")
_REL_TO = re.compile(r"^\ttoColumn:\s*(.+)$")
# 'Table name'[Column] or table_name[Column]; the table part must not be preceded by a word character.
_QUALIFIED_REF = re.compile(r"(?<![\w\]])('(?:[^']|'')+'|[A-Za-z_]\w*)\[([^\]]+)\]")
_BARE_REF = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
_DAX_STRING = re.compile(r'"(?:[^"]|"")*"')
_DAX_COMMENT = re.compile(r"//[^\n]*|--[^\n]*")


def unquote(name: str) -> str:
    """TMDL / DAX object name without its single quotes (``'Income basis'`` -> ``Income basis``)."""
    name = name.strip()
    if name.startswith("'") and name.endswith("'"):
        return name[1:-1].replace("''", "'")
    return name


def _split_qualified(ref: str) -> tuple[str, str]:
    """``table.column`` of a relationship end (either part may be quoted)."""
    match = re.fullmatch(rf"({_NAME})\.({_NAME})", ref.strip())
    if not match:
        raise ValueError(f"cannot parse relationship column {ref!r}")
    return unquote(match.group(1)), unquote(match.group(2))


def parse_model(folder: Path) -> ParsedModel:
    """Read tables, columns (with dataType), measures, sort-by columns and relationships from a TMDL folder."""
    model = ParsedModel()
    for path in sorted((folder / "tables").glob("*.tmdl")):
        table: str | None = None
        current_column: str | None = None
        current_measure: str | None = None
        expr_lines: list[str] = []
        in_fence = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if current_measure is not None:
                # Expression lines are indented deeper than the measure's properties (3+ tabs) or fenced by ```.
                if line.strip() == "```":
                    in_fence = not in_fence
                    continue
                if in_fence or line.startswith("\t\t\t") or (not line.strip() and not expr_lines):
                    expr_lines.append(line)
                    continue
                model.measures[current_measure] = "\n".join(expr_lines)
                current_measure = None
            if m := _TABLE_RE.match(line):
                table = unquote(m.group(1))
                model.columns.setdefault(table, {})
                current_column = None
            elif (m := _COLUMN_RE.match(line)) and table is not None:
                current_column = unquote(m.group(1))
                model.columns[table][current_column] = None
            elif m := _MEASURE_RE.match(line):
                current_column = None
                current_measure = unquote(m.group(1))
                first = m.group(2).strip()
                in_fence = first == "```"
                expr_lines = [] if first in {"", "```"} else [first]
            elif (m := _PROP_RE.match(line)) and table is not None and current_column is not None:
                prop, value = m.group(1), (m.group(2) or "").strip()
                if prop == "dataType":
                    model.columns[table][current_column] = value
                elif prop == "sortByColumn":
                    model.sort_by.append((table, current_column, unquote(value)))
            elif line.startswith("\t") and not line.startswith("\t\t"):
                current_column = None  # partition, annotation, hierarchy ... ends the column block
        if current_measure is not None:
            model.measures[current_measure] = "\n".join(expr_lines)
    relationships = folder / "relationships.tmdl"
    if relationships.exists():
        pending_from: str | None = None
        for line in relationships.read_text(encoding="utf-8").splitlines():
            if m := _REL_FROM.match(line):
                pending_from = m.group(1)
            elif (m := _REL_TO.match(line)) and pending_from is not None:
                model.relationships.append((pending_from, m.group(1)))
                pending_from = None
    return model


def dax_references(expression: str) -> tuple[set[tuple[str, str]], set[str]]:
    """(table, column) references and bare ``[name]`` references in a DAX expression (strings, comments ignored)."""
    code = _DAX_COMMENT.sub("", _DAX_STRING.sub('""', expression))
    qualified = {(unquote(t), c) for t, c in _QUALIFIED_REF.findall(code)}
    without_qualified = _QUALIFIED_REF.sub("", code)
    bare = set(_BARE_REF.findall(without_qualified))
    return qualified, bare


def check_model(model: ParsedModel, mart_columns: dict[str, list[tuple[str, str]]]) -> list[str]:
    """Problems of a parsed model against the exported marts (empty list = consistent)."""
    problems: list[str] = []
    for table, columns in mart_columns.items():
        if table not in model.columns:
            problems.append(f"table {table}: missing from the model")
            continue
        expected = {name: _TYPE_MAP.get(duck_type, duck_type) for name, duck_type in columns}
        actual = model.columns[table]
        for name, data_type in expected.items():
            if name not in actual:
                problems.append(f"{table}.{name}: in the mart, missing from the model")
            elif actual[name] != data_type:
                problems.append(f"{table}.{name}: dataType {actual[name]} in the model, {data_type} in the mart")
        for name in sorted(set(actual) - set(expected)):
            problems.append(f"{table}.{name}: in the model, not in the mart")
    for table, column, sort_by in model.sort_by:
        if sort_by not in model.columns.get(table, {}):
            problems.append(f"{table}.{column}: sort-by column {sort_by} does not exist")
    for ends in model.relationships:
        for end in ends:
            table, column = _split_qualified(end)
            if column not in model.columns.get(table, {}):
                problems.append(f"relationship {ends[0]} -> {ends[1]}: {table}.{column} does not exist")
    for measure, expression in sorted(model.measures.items()):
        qualified, bare = dax_references(expression)
        for table, column in sorted(qualified):
            if table not in model.columns:
                problems.append(f"measure [{measure}]: table {table!r} does not exist")
            elif column not in model.columns[table] and column not in model.measures:
                problems.append(f"measure [{measure}]: {table}[{column}] does not exist")
        for name in sorted(bare):
            if not name.startswith("@") and name not in model.measures:
                problems.append(f"measure [{measure}]: [{name}] is not a measure")
    return problems


def check(root: Path = config.REPO_ROOT) -> list[str]:
    """Compare the TMDL model with the exported Parquet files and lint the DAX references."""
    parquet_dir = export.export_dir(root)
    mart_columns = {}
    for table in MART_TABLES:
        source = parquet_dir / f"{table}.parquet"
        if not source.exists():
            raise FileNotFoundError(f"{source} not found - run `make export` first")
        mart_columns[table] = parquet_columns(source)
    return check_model(parse_model(definition_dir(root)), mart_columns)


# --- expected values (powerbi/CHECKS.md) -------------------------------------------------------------------

# Municipalities on the detail page checklist: the G4, the least affordable one, one too small to be ranked.
CHECK_MUNICIPALITIES = ("GM0363", "GM0599", "GM0518", "GM0344", "GM0417", "GM0088")

_EXPECTED_MUNICIPAL_SQL = """
with
years as (
    select
        min(year)                                         as y0,
        max(case when is_latest_final_year then year end) as y1
    from marts.dim_year
),
f as (
    select f.*, d.municipality_name
    from marts.fct_affordability as f
    join marts.dim_municipality as d using (municipality_code)
),
-- D-035: ranks are recomputed on the municipalities ranked in both years
panel as (
    select a.municipality_code
    from f as a
    join f as b on b.municipality_code = a.municipality_code
    where a.year = (select y0 from years) and b.year = (select y1 from years)
      and a.pti_rank_desc is not null and b.pti_rank_desc is not null
),
panel_ranks as (
    select
        municipality_code,
        year,
        rank() over (partition by year order by price_to_income_ratio desc)        as r_all,
        rank() over (partition by year order by price_to_income_owner_ratio desc)  as r_owner
    from f
    where municipality_code in (select municipality_code from panel)
      and year in ((select y0 from years), (select y1 from years))
),
base as (
    select * from f where year = (select y0 from years)
),
latest as (
    select * from f where year = (select y1 from years)
)
select
    l.municipality_code,
    l.municipality_name,
    l.price_to_income_ratio,
    l.price_to_income_owner_ratio,
    l.pti_rank_desc,
    l.pti_owner_rank_desc,
    l.low_reliability,
    p0.r_all - p1.r_all                                                        as rank_change_all,
    p0.r_owner - p1.r_owner                                                    as rank_change_owner,
    l.avg_sale_price_eur / b.avg_sale_price_eur - 1                            as price_growth,
    l.median_disposable_income_eur / b.median_disposable_income_eur - 1        as income_growth,
    (l.avg_sale_price_eur / b.avg_sale_price_eur
        - l.median_disposable_income_eur / b.median_disposable_income_eur) * 100  as growth_gap_pp,
    l.owner_households_count / l.households_count                              as owner_share
from latest as l
join base as b using (municipality_code)
left join panel_ranks as p0 on p0.municipality_code = l.municipality_code and p0.year = (select y0 from years)
left join panel_ranks as p1 on p1.municipality_code = l.municipality_code and p1.year = (select y1 from years)
where l.municipality_code in ({codes})
order by l.pti_rank_desc nulls last
"""


def _fmt(value: float | int | None, kind: str) -> str:
    """Value as Power BI shows it with the measure's format string."""
    if value is None:
        return "(blank)"
    formats = {
        "pti": f"{value:.2f}",
        "x": f"{value:.2f}×",
        "pct": f"{value:+.1%}",
        "share": f"{value:.0%}",
        "pp": f"{value:+.1f} pp",
        "int": f"{value:.0f}",
        "signed": f"{value:+.0f}",
    }
    return formats[kind]


def expected_values(con: duckdb.DuckDBPyConnection) -> str:
    """Markdown checklist of the values the DAX measures must show, computed in SQL from the marts."""
    y0, y1, y_last, n_years = con.execute(
        "select min(year), max(case when is_latest_final_year then year end), "
        "max(case when is_latest_data_year then year end), count(*) from marts.dim_year"
    ).fetchone()
    label = dict(con.execute("select year, year_label from marts.dim_year").fetchall())

    def group(col: str, gtype: str, gcode: str, year: int) -> float:
        return con.execute(
            f"select {col} from marts.fct_group_affordability where group_type = ? and group_code = ? and year = ?",
            [gtype, gcode, year],
        ).fetchone()[0]

    def gap(year: int, owner: bool) -> float:
        col = "price_to_income_owner_ratio" if owner else "price_to_income_ratio"
        return group(col, "region_group", "G4", year) / group(col, "region_group", "REST_NL", year)

    def share_outgrew(owner: bool) -> float:
        inc = "median_disposable_income_owner_eur" if owner else "median_disposable_income_eur"
        return con.execute(
            f"""
            select avg(case when l.avg_sale_price_eur / b.avg_sale_price_eur > l.{inc} / b.{inc} then 1.0 else 0 end)
            from marts.fct_affordability as l
            join marts.fct_affordability as b on b.municipality_code = l.municipality_code and b.year = ?
            where l.year = ? and l.avg_sale_price_eur / b.avg_sale_price_eur is not null
              and l.{inc} / b.{inc} is not null
            """,
            [y0, y1],
        ).fetchone()[0]

    counts = [
        con.execute(f"select count(*) from marts.{t}").fetchone()[0]
        for t in ("fct_affordability", "fct_group_affordability", "dim_municipality", "dim_province", "dim_year")
    ]
    ranked = con.execute("select count(pti_rank_desc) from marts.fct_affordability where year = ?", [y1]).fetchone()[0]

    def pti(gtype: str, gcode: str, year: int, owner: bool = False) -> str:
        col = "price_to_income_owner_ratio" if owner else "price_to_income_ratio"
        return _fmt(group(col, gtype, gcode, year), "pti")

    def growth(col: str, gtype: str, gcode: str) -> str:
        return _fmt(group(col, gtype, gcode, y1) / group(col, gtype, gcode, y0) - 1, "pct")

    share = "owner_households_count / households_count"
    lines = [
        "# Power BI control values",
        "",
        "_Generated by `python -m nl_housing.powerbi expected` from the DuckDB marts; do not edit by hand._",
        "The DAX measures are not executed outside Power BI. Every value below is computed **independently in SQL**",
        "with the same definition as the measure. After a refresh, put each measure on the *Model checks* page",
        "(a card or a table) and compare. A mismatch means a wrong measure, filter or relationship, not new data.",
        "",
        f"Defaults: no year selected → report year = latest final year **{y1}**; base year **{y0}**; income basis",
        "**All households** (slicer empty or on *All households*).",
        "",
        "## 1. Model",
        "",
        "| Measure | Expected |",
        "|---|---:|",
        f"| `Check row counts` | OK: {' / '.join(str(c) for c in counts)} |",
        "| `Check orphan keys` | OK: 0 orphan rows |",
        f"| `Latest final year` / `Report year` | {y1} |",
        f"| `Base year` | {y0} |",
        f"| `Ranked municipalities` | {ranked} |",
        "",
        "## 2. Headline cards (no filters)",
        "",
        "| Measure | All households | Owner-occupiers (slicer) |",
        "|---|---:|---:|",
        f"| `PTI Netherlands` | {pti('nl', 'NL01', y1)} | {pti('nl', 'NL01', y1, True)} |",
        f"| `PTI G4` | {pti('region_group', 'G4', y1)} | {pti('region_group', 'G4', y1, True)} |",
        f"| `PTI Rest of NL` | {pti('region_group', 'REST_NL', y1)} | {pti('region_group', 'REST_NL', y1, True)} |",
        f"| `PTI Rest of Randstad provinces` | {pti('region_group_3', 'REST_RANDSTAD', y1)} "
        f"| {pti('region_group_3', 'REST_RANDSTAD', y1, True)} |",
        f"| `G4 ÷ Rest of NL` | {_fmt(gap(y1, False), 'x')} | {_fmt(gap(y1, True), 'x')} |",
        f"| `Share of municipalities where prices outgrew incomes` | {_fmt(share_outgrew(False), 'share')} "
        f"| {_fmt(share_outgrew(True), 'share')} |",
        f"| `Owner-occupier share G4` | {_fmt(group(share, 'region_group', 'G4', y1), 'share')} | same |",
        f"| `Owner-occupier share Rest of NL` | {_fmt(group(share, 'region_group', 'REST_NL', y1), 'share')} | same |",
        "",
        "`G4 ÷ Rest of NL (all households)` and `(owner-occupiers)` must show the two columns of that row whatever the",
        "slicer says.",
        "",
        "## 3. Over time (line chart on `dim_year[year_label]`, or a year slicer)",
        "",
        "| Year | `PTI Netherlands` | `G4 ÷ Rest of NL (all households)` | `G4 ÷ Rest of NL (owner-occupiers)` |",
        "|---|---:|---:|---:|",
    ]
    for year in (y0, y1, y_last):
        gaps = f"{_fmt(gap(year, False), 'x')} | {_fmt(gap(year, True), 'x')}"
        lines.append(f"| {label[year]} | {pti('nl', 'NL01', year)} | {gaps} |")
    lines += [
        "",
        f"Group growth {y0}→{y1} (all households; `Group price growth since base year` /",
        "`Group income growth since base year`, table with `group_name`, page filter `group_type = region_group`):",
        "",
        "| Group | Price growth | Income growth |",
        "|---|---:|---:|",
    ]
    for gcode, name in (("G4", "G4"), ("REST_NL", "Rest of NL")):
        lines.append(
            f"| {name} | {growth('avg_sale_price_eur', 'region_group', gcode)} "
            f"| {growth('median_disposable_income_eur', 'region_group', gcode)} |"
        )
    lines += [
        "",
        f"## 4. Municipality detail ({y1}, table with `dim_municipality[municipality_name]`)",
        "",
        "| Municipality | `PTI` | `PTI (owner-occupiers)` | `PTI rank label` | `PTI rank (owner-occupiers)` "
        "| `PTI rank change since base year` (all / owner) | `Price growth since base year` "
        "| `Income growth since base year` | `Growth gap (pp)` | `Owner-occupier share` |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    codes = ", ".join(f"'{c}'" for c in CHECK_MUNICIPALITIES)
    for row in con.execute(_EXPECTED_MUNICIPAL_SQL.format(codes=codes)).fetchall():
        (_, name, p_all, p_own, r_all, r_own, small, rc_all, rc_own, pg, ig, gp, share) = row
        rank_label = (
            f"{r_all} of {ranked}"
            if r_all is not None
            else ("not ranked: fewer than 5 000 households" if small else "not ranked: no PTI")
        )
        lines.append(
            f"| {name} | {_fmt(p_all, 'pti')} | {_fmt(p_own, 'pti')} | {rank_label} | {_fmt(r_own, 'int')} "
            f"| {_fmt(rc_all, 'signed')} / {_fmt(rc_own, 'signed')} | {_fmt(pg, 'pct')} | {_fmt(ig, 'pct')} "
            f"| {_fmt(gp, 'pp')} | {_fmt(share, 'share')} |"
        )
    lines += [
        "",
        "Rank change: positive = the municipality moved towards the least-affordable end (rank number fell), on the",
        f"municipalities ranked in both {y0} and {y1} (D-035). With the slicer on *Owner-occupiers*, `PTI`, `PTI rank`",
        "and `Income growth since base year` switch to the owner-occupier columns.",
        f"`Report year label` for {y_last} must read `{label[y_last]}`; `Preliminary note` is empty for {y1}.",
        "",
    ]
    if n_years != len(label):  # pragma: no cover - dim_year has one row per year by construction
        raise ValueError("dim_year has duplicate years")
    return "\n".join(lines)


def write_expected(root: Path = config.REPO_ROOT, db_path: Path | None = None) -> Path:
    """Write ``powerbi/CHECKS.md`` from the built DuckDB database."""
    db_path = db_path or config.duckdb_path(root)
    with duckdb.connect(str(db_path), read_only=True) as con:
        text = expected_values(con)
    target = project_dir(root) / "CHECKS.md"
    target.write_text(text, encoding="utf-8")
    logger.info("Wrote %s", target.relative_to(root))
    return target


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    scaffold_cmd = sub.add_parser("scaffold", help="write tables/<mart>.tmdl from data/processed/marts/*.parquet")
    scaffold_cmd.add_argument("--force", action="store_true", help="overwrite existing table files")
    sub.add_parser("check", help="check the model against the marts and lint DAX references")
    sub.add_parser("expected", help="write powerbi/CHECKS.md (control values) from the built database")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "scaffold":
        scaffold(force=args.force)
        return 0
    if args.command == "expected":
        write_expected()
        return 0
    problems = check()
    for problem in problems:
        logger.error(problem)
    model = parse_model(definition_dir())
    logger.info(
        "Power BI model: %d tables, %d measures, %d relationships, %d problem(s)",
        len(model.columns),
        len(model.measures),
        len(model.relationships),
        len(problems),
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
