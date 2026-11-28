"""Offline tests for the SQL runner (``nl_housing.transform``) with a tiny DuckDB in tmp_path."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nl_housing import config, transform
from nl_housing.transform import TransformError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A repo root with a raw table, two staging models (one depends on the other) and a mart."""
    db = config.duckdb_path(tmp_path)
    db.parent.mkdir(parents=True)
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE SCHEMA raw")
        con.execute("CREATE TABLE raw.cbs_x AS SELECT * FROM (VALUES ('GM0363  ', 1), ('NL01  ', 2)) t(code, v)")

    sql = tmp_path / "sql"
    (sql / "staging").mkdir(parents=True)
    (sql / "marts").mkdir()
    (sql / "staging" / "stg_a.sql").write_text(
        "-- header comment\nwith source as (select trim(code) as code, v from raw.cbs_x)\nselect * from source;\n"
    )
    (sql / "staging" / "stg_b.sql").write_text("select code, v * 10 as v10 from staging.stg_a -- trailing comment")
    (sql / "marts" / "dim_x.sql").write_text("select code from staging.stg_b where code like 'GM%'")
    (sql / "models.yaml").write_text("staging:\n  - stg_a\n  - stg_b\nmarts:\n  - dim_x\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "cbs_tables.yaml").write_text(PROJECT_CONFIG)
    return tmp_path


PROJECT_CONFIG = """
project:
  analysis_years: [2011, 2013]
  randstad_g4: [GM0363, GM0599]
  randstad_provinces: [PV27]
  low_reliability_max_households: 5000
tables: []
"""


def _query(root: Path, sql: str) -> list[tuple]:
    with duckdb.connect(str(config.duckdb_path(root)), read_only=True) as con:
        return con.execute(sql).fetchall()


def test_load_models_in_listed_order(project: Path):
    models = transform.load_models(project)
    assert [m.table for m in models] == ["staging.stg_a", "staging.stg_b", "marts.dim_x"]


def test_run_builds_tables_in_order(project: Path):
    counts = transform.run(root=project)
    assert counts == {"staging.stg_a": 2, "staging.stg_b": 2, "marts.dim_x": 1}
    assert _query(project, "select code, v10 from staging.stg_b order by code") == [("GM0363", 10), ("NL01", 20)]
    assert _query(project, "select * from marts.dim_x") == [("GM0363",)]


def test_run_is_idempotent(project: Path):
    first = transform.run(root=project)
    second = transform.run(root=project)
    assert first == second


def test_empty_layer_is_allowed(project: Path):
    (project / "sql" / "marts" / "dim_x.sql").unlink()
    (project / "sql" / "models.yaml").write_text("staging:\n  - stg_a\nmarts: []\n")
    (project / "sql" / "staging" / "stg_b.sql").unlink()
    assert transform.run(root=project) == {"staging.stg_a": 2}
    assert _query(project, "select count(*) from information_schema.schemata where schema_name = 'marts'") == [(1,)]


@pytest.mark.parametrize(
    ("models_yaml", "message"),
    [
        ("staging:\n  - stg_a\n  - stg_b\n  - stg_missing\nmarts:\n  - dim_x\n", "does not exist"),
        ("staging:\n  - stg_a\nmarts:\n  - dim_x\n", "not listed"),
        ("staging:\n  - stg_a\n  - stg_b\n  - stg_a\nmarts:\n  - dim_x\n", "more than once"),
        ("staging:\n  - Stg-A\n", "Invalid model"),
        ("- stg_a\n", "must map"),
    ],
)
def test_invalid_model_list_raises(project: Path, models_yaml: str, message: str):
    (project / "sql" / "models.yaml").write_text(models_yaml)
    with pytest.raises(TransformError, match=message):
        transform.load_models(project)


@pytest.mark.parametrize(
    "sql_text",
    ["select 1; select 2", "create table t as select 1", "-- only a comment", "selec 1"],
)
def test_model_must_be_a_single_select(project: Path, sql_text: str):
    (project / "sql" / "marts" / "dim_x.sql").write_text(sql_text)
    with pytest.raises(TransformError):
        transform.run(root=project)


def test_failure_rolls_back_all_models(project: Path):
    transform.run(root=project)
    # Change stg_a, then break the mart: the new stg_a must not be committed.
    (project / "sql" / "staging" / "stg_a.sql").write_text("select 'changed' as code, 0 as v")
    (project / "sql" / "marts" / "dim_x.sql").write_text("select * from staging.does_not_exist")
    with pytest.raises(duckdb.Error):
        transform.run(root=project)
    assert _query(project, "select count(*) from staging.stg_a") == [(2,)]


def test_missing_database_raises(project: Path):
    config.duckdb_path(project).unlink()
    with pytest.raises(TransformError, match="make load"):
        transform.run(root=project)


def test_repo_model_list_matches_sql_folders():
    """The committed sql/models.yaml must list exactly the committed .sql files."""
    models = transform.load_models(config.REPO_ROOT)
    assert all(m.path.exists() for m in models)


def test_removed_model_table_is_dropped(project: Path):
    """QA P-3: a model removed from models.yaml must not leave a stale table behind."""
    transform.run(root=project)
    with duckdb.connect(str(config.duckdb_path(project))) as con:
        con.execute("CREATE VIEW marts.v_old AS SELECT 1 AS x")
    (project / "sql" / "marts" / "dim_x.sql").rename(project / "sql" / "marts" / "dim_y.sql")
    (project / "sql" / "models.yaml").write_text("staging:\n  - stg_a\n  - stg_b\nmarts:\n  - dim_y\n")

    transform.run(root=project)
    tables = _query(project, "select schema_name, table_name from duckdb_tables() order by 1, 2")
    views = _query(project, "select view_name from duckdb_views() where schema_name = 'marts'")
    assert ("marts", "dim_x") not in tables and ("marts", "dim_y") in tables
    assert ("raw", "cbs_x") in tables  # other schemas are not touched
    assert views == []


def test_drop_of_stale_tables_is_rolled_back_on_failure(project: Path):
    transform.run(root=project)
    (project / "sql" / "marts" / "dim_x.sql").rename(project / "sql" / "marts" / "dim_y.sql")
    (project / "sql" / "marts" / "dim_y.sql").write_text("select * from staging.does_not_exist")
    (project / "sql" / "models.yaml").write_text("staging:\n  - stg_a\n  - stg_b\nmarts:\n  - dim_y\n")
    with pytest.raises(duckdb.Error):
        transform.run(root=project)
    assert _query(project, "select count(*) from marts.dim_x") == [(1,)]


def test_project_settings_are_written_before_the_models(project: Path):
    """Models read the analysis window from reference.project_settings (config = single source of truth)."""
    (project / "sql" / "marts" / "dim_x.sql").write_text(
        "select unnest(range(year_from, year_to + 1)) as year, g4_codes from reference.project_settings"
    )
    transform.run(root=project)
    assert _query(project, "select year from marts.dim_x order by year") == [(2011,), (2012,), (2013,)]
    assert _query(project, "select base_year, g4_codes, randstad_province_codes from reference.project_settings") == [
        (2011, ["GM0363", "GM0599"], ["PV27"])
    ]


def test_config_change_takes_effect_on_next_run(project: Path):
    transform.run(root=project)
    (project / "config" / "cbs_tables.yaml").write_text(PROJECT_CONFIG.replace("[2011, 2013]", "[2012, 2020]"))
    transform.run(root=project)
    assert _query(project, "select year_from, year_to from reference.project_settings") == [(2012, 2020)]


def test_missing_project_section_fails_before_any_model(project: Path):
    (project / "config" / "cbs_tables.yaml").write_text("tables: []\n")
    with pytest.raises(config.ConfigError, match="project"):
        transform.run(root=project)
    assert _query(project, "select count(*) from duckdb_tables() where schema_name = 'staging'") == [(0,)]
