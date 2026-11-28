"""Offline tests for nl_housing.powerbi (TMDL scaffold and drift / DAX-reference check)."""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

from nl_housing import config, export, powerbi

COMMITTED_MODEL = powerbi.definition_dir(config.REPO_ROOT)


def _write_parquet(root: Path, table: str, select: str) -> None:
    out = export.export_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute(f"copy ({select}) to '{(out / f'{table}.parquet').as_posix()}' (format parquet)")


def _minimal_marts(root: Path) -> None:
    """Tiny Parquet files with the mart names, enough to scaffold and check a model."""
    _write_parquet(root, "dim_municipality", "select 'GM0363' as municipality_code, 'PV27' as province_code")
    _write_parquet(root, "dim_province", "select 'PV27' as province_code, true as is_randstad_province")
    _write_parquet(root, "dim_year", "select 2011::integer as year, '2011' as year_label, 0 as years_since_base")
    _write_parquet(
        root,
        "fct_affordability",
        "select 'GM0363' as municipality_code, 2011::integer as year, 1.5::double as price_to_income_ratio, "
        "3::bigint as pti_rank_desc",
    )
    _write_parquet(root, "fct_group_affordability", "select 2011::integer as year, 'nl' as group_type")


def _measures(folder: Path, body: str) -> None:
    (folder / "tables" / "_Measures.tmdl").write_text(
        "table _Measures\n\n" + body + "\n\tcolumn Value\n\t\tisHidden\n\t\tsourceColumn: [Value]\n", encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("column", "data_type", "expected"),
    [
        ("year", "int64", "0"),
        ("pti_rank_desc", "int64", "0"),
        ("avg_sale_price_eur", "double", "#,0"),
        ("real_avg_sale_price_eur_2025", "double", "#,0"),
        ("price_to_income_ratio", "double", "0.00"),
        ("growth_gap_pp", "double", "0.0"),
        ("households_count", "double", "#,0"),
        ("group_name", "string", None),
        ("is_g4", "boolean", None),
    ],
)
def test_format_string_from_suffix(column: str, data_type: str, expected: str | None) -> None:
    assert powerbi.format_string(column, data_type) == expected


def test_scaffold_writes_tables_and_keeps_existing(tmp_path: Path) -> None:
    _minimal_marts(tmp_path)
    written = powerbi.scaffold(root=tmp_path)
    assert sorted(p.stem for p in written) == sorted(powerbi.MART_TABLES)

    text = (powerbi.definition_dir(tmp_path) / "tables" / "dim_year.tmdl").read_text(encoding="utf-8")
    assert "\tcolumn year_label\n\t\tdataType: string\n" in text
    assert "\t\tsortByColumn: year\n" in text  # year_label sorts by year
    assert '"\\dim_year.parquet"' in text  # Power Query reads the exported file via the MartsFolder parameter

    target = powerbi.definition_dir(tmp_path) / "tables" / "dim_year.tmdl"
    target.write_text("edited in Power BI Desktop", encoding="utf-8")
    assert powerbi.scaffold(root=tmp_path) == []  # existing files are kept
    assert target.read_text(encoding="utf-8") == "edited in Power BI Desktop"
    assert len(powerbi.scaffold(root=tmp_path, force=True)) == len(powerbi.MART_TABLES)


def test_lineage_tags_are_stable(tmp_path: Path) -> None:
    _minimal_marts(tmp_path)
    powerbi.scaffold(root=tmp_path)
    first = (powerbi.definition_dir(tmp_path) / "tables" / "fct_affordability.tmdl").read_text(encoding="utf-8")
    powerbi.scaffold(root=tmp_path, force=True)
    assert (powerbi.definition_dir(tmp_path) / "tables" / "fct_affordability.tmdl").read_text(encoding="utf-8") == first


def test_check_passes_on_consistent_model(tmp_path: Path) -> None:
    _minimal_marts(tmp_path)
    powerbi.scaffold(root=tmp_path)
    folder = powerbi.definition_dir(tmp_path)
    _measures(
        folder,
        "\tmeasure 'Report year' = MAX ( dim_year[year] )\n\n"
        "\tmeasure PTI = ```\n"
        "\t\t\tVAR y = [Report year]   // a comment with [Not a measure]\n"
        '\t\t\tVAR label = "text with [brackets]"\n'
        "\t\t\tRETURN CALCULATE ( SELECTEDVALUE ( fct_affordability[price_to_income_ratio] ), dim_year[year] = y )\n"
        "\t\t\t```\n"
        "\t\tformatString: 0.00\n",
    )
    (folder / "relationships.tmdl").write_text(
        "relationship r1\n\tfromColumn: fct_affordability.municipality_code\n"
        "\ttoColumn: dim_municipality.municipality_code\n",
        encoding="utf-8",
    )
    assert powerbi.check(root=tmp_path) == []


def test_check_reports_drift_and_bad_references(tmp_path: Path) -> None:
    _minimal_marts(tmp_path)
    powerbi.scaffold(root=tmp_path)
    folder = powerbi.definition_dir(tmp_path)
    # the mart gains a column and changes a type after the model was scaffolded
    _write_parquet(
        tmp_path,
        "fct_affordability",
        "select 'GM0363' as municipality_code, 2011::integer as year, '1.5' as price_to_income_ratio, "
        "3::bigint as pti_rank_desc, 1::bigint as new_column",
    )
    _measures(
        folder,
        "\tmeasure A = SUM ( fct_affordability[no_such_column] ) + [No such measure]\n\n"
        "\tmeasure B = COUNTROWS ( 'No such table' ) + SUM ( 'No such table'[x] )\n\n"
        "\tmeasure C = SUMX ( FILTER ( VALUES ( dim_year[year] ), [@ok] > 0 ), [A] )\n",
    )
    (folder / "relationships.tmdl").write_text(
        "relationship r1\n\tfromColumn: fct_affordability.missing_key\n\ttoColumn: dim_year.year\n", encoding="utf-8"
    )
    problems = powerbi.check(root=tmp_path)
    assert "fct_affordability.new_column: in the mart, missing from the model" in problems
    assert "fct_affordability.price_to_income_ratio: dataType double in the model, string in the mart" in problems
    assert "measure [A]: fct_affordability[no_such_column] does not exist" in problems
    assert "measure [A]: [No such measure] is not a measure" in problems
    assert "measure [B]: table 'No such table' does not exist" in problems
    assert any("relationship" in p and "missing_key" in p for p in problems)
    assert not any("measure [C]" in p for p in problems)  # [@ok] is a column made inside the expression


def test_committed_model_references_are_consistent(tmp_path: Path) -> None:
    """The committed TMDL: every DAX reference, sort-by and relationship column exists in the model itself."""
    model = powerbi.parse_model(COMMITTED_MODEL)
    assert set(powerbi.MART_TABLES) <= set(model.columns)
    assert {"_Measures", "Income basis"} <= set(model.columns)
    assert len(model.measures) >= 40
    assert len(model.relationships) == 4
    # Use the model's own mart columns as the "marts": only reference, sort-by and relationship problems remain.
    inverse = {v: k for k, v in powerbi._TYPE_MAP.items() if k in {"VARCHAR", "BOOLEAN", "BIGINT", "DOUBLE"}}
    marts = {t: [(c, inverse[d]) for c, d in model.columns[t].items()] for t in powerbi.MART_TABLES}
    assert powerbi.check_model(model, marts) == []


def test_committed_measures_follow_income_basis_rule() -> None:
    """D-038: every measure that reads an all-household PTI / income / rank column also reads the owner column."""
    model = powerbi.parse_model(COMMITTED_MODEL)
    pairs = {
        "price_to_income_ratio": "price_to_income_owner_ratio",
        "median_disposable_income_eur": "median_disposable_income_owner_eur",
        "pti_rank_desc": "pti_owner_rank_desc",
    }
    for name, expression in model.measures.items():
        if name.startswith("Check"):
            continue
        for all_col, owner_col in pairs.items():
            if f"[{all_col}]" in expression:
                assert f"[{owner_col}]" in expression, f"[{name}] reads {all_col} but ignores the income basis"


def test_scaffold_requires_export(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make export"):
        powerbi.scaffold(root=tmp_path)


def test_unquote_and_references() -> None:
    assert powerbi.unquote("'Income basis'") == "Income basis"
    assert powerbi.unquote("'It''s'") == "It's"
    qualified, bare = powerbi.dax_references("CALCULATE ( [PTI], 'Income basis'[basis_key] = \"all\" ) // [x]")
    assert qualified == {("Income basis", "basis_key")}
    assert bare == {"PTI"}


def test_committed_model_copy_checks_against_minimal_marts(tmp_path: Path) -> None:
    """A copied committed model run against different marts reports drift (the check reads real files)."""
    shutil.copytree(COMMITTED_MODEL, powerbi.definition_dir(tmp_path))
    _minimal_marts(tmp_path)
    problems = powerbi.check(root=tmp_path)
    assert any(p.endswith("in the model, not in the mart") for p in problems)


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [
        (9.2361, "pti", "9.24"),
        (1.38997, "x", "1.39×"),
        (1.0821, "pct", "+108.2%"),
        (0.3598, "share", "36%"),
        (27.68, "pp", "+27.7 pp"),
        (5, "signed", "+5"),
        (None, "pti", "(blank)"),
    ],
)
def test_expected_values_use_the_measure_formats(value: float | None, kind: str, expected: str) -> None:
    assert powerbi._fmt(value, kind) == expected
