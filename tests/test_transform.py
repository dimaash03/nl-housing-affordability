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
    return tmp_path


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


def test_relative_paths_resolve_against_repo_root(project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory):
    """A model may read a committed reference file by repo-relative path, whatever the working directory."""
    (project / "data" / "reference").mkdir(parents=True)
    (project / "data" / "reference" / "ref.csv").write_text("code,w\nGM0363,0.5\n")
    (project / "sql" / "marts" / "dim_x.sql").write_text("select code, w from read_csv('data/reference/ref.csv')")
    monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))
    transform.run(root=project)
    assert _query(project, "select code, w from marts.dim_x") == [("GM0363", 0.5)]


def test_missing_database_raises(project: Path):
    config.duckdb_path(project).unlink()
    with pytest.raises(TransformError, match="make load"):
        transform.run(root=project)


def test_repo_model_list_matches_sql_folders():
    """The committed sql/models.yaml must list exactly the committed .sql files."""
    models = transform.load_models(config.REPO_ROOT)
    assert all(m.path.exists() for m in models)
