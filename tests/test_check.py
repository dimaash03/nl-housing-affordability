"""Offline tests for the SQL data-test runner (``nl_housing.check``)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nl_housing import check, config


@pytest.fixture
def project(tmp_path: Path) -> Path:
    db = config.duckdb_path(tmp_path)
    db.parent.mkdir(parents=True)
    with duckdb.connect(str(db)) as con:
        for schema in check.REQUIRED_SCHEMAS:
            con.execute(f"CREATE SCHEMA {schema}")
        con.execute("CREATE TABLE reference.project_settings AS SELECT 2011 AS year_from")
        con.execute("CREATE TABLE staging.t AS SELECT * FROM (VALUES ('GM1', 1), ('GM1', 2), ('GM2', -5)) v(code, x)")
    (tmp_path / "sql" / "tests").mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize(
    ("drop", "hint"),
    [
        ("DROP SCHEMA staging CASCADE", "run `make transform`"),
        ("DROP SCHEMA raw CASCADE", "run `make load transform`"),
        ("DROP TABLE reference.project_settings", "reference.project_settings is missing"),
    ],
)
def test_unbuilt_database_names_the_missing_step(project: Path, drop: str, hint: str):
    _write(project, "assert_anything", "select * from staging.t where x < 0")
    with duckdb.connect(str(config.duckdb_path(project))) as con:
        con.execute(drop)
    with pytest.raises(check.CheckSetupError, match=hint):
        check.run(root=project)


def test_main_returns_1_on_unbuilt_database(monkeypatch: pytest.MonkeyPatch):
    def not_built() -> list[check.CheckResult]:
        raise check.CheckSetupError("run `make transform` before `make check`")

    monkeypatch.setattr(check, "run", not_built)
    assert check.main([]) == 1


def _write(root: Path, name: str, sql: str) -> None:
    (root / "sql" / "tests" / f"{name}.sql").write_text(sql)


def test_passing_and_failing_checks(project: Path):
    _write(project, "assert_no_nulls", "-- expect none\nselect * from staging.t where code is null;")
    _write(project, "assert_unique_code", "select code, count(*) as n from staging.t group by code having n > 1")
    _write(project, "assert_non_negative", "select * from staging.t where x < 0")

    results = {r.name: r for r in check.run(root=project)}

    assert results["assert_no_nulls"].passed
    dup = results["assert_unique_code"]
    assert not dup.passed and dup.failing_rows == 1 and dup.sample == [("GM1", 2)]
    assert dup.columns == ["code", "n"]
    assert results["assert_non_negative"].failing_rows == 1


def test_sql_error_is_reported_as_failed_check(project: Path):
    _write(project, "assert_broken", "select * from staging.does_not_exist")
    _write(project, "assert_two_statements", "select 1; select 2")
    results = check.run(root=project)
    assert all(not r.passed and r.error for r in results)


def test_checks_run_read_only(project: Path):
    _write(project, "assert_sneaky_write", "create table staging.x as select 1")
    (result,) = check.run(root=project)
    assert not result.passed
    with duckdb.connect(str(config.duckdb_path(project)), read_only=True) as con:
        tables = con.execute("select table_name from information_schema.tables where table_name = 'x'").fetchall()
    assert tables == []


def test_main_exit_codes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(check, "run", lambda: [check.CheckResult("ok", 0)])
    assert check.main([]) == 0
    monkeypatch.setattr(check, "run", lambda: [check.CheckResult("bad", 3)])
    assert check.main([]) == 1
    monkeypatch.setattr(check, "run", lambda: [])  # no checks found is a failure, not a silent pass
    assert check.main([]) == 1


def test_missing_database_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        check.run(root=tmp_path)


def test_repo_checks_are_single_selects():
    """Every committed sql/tests/*.sql must parse as exactly one SELECT."""
    paths = sorted(check.tests_dir(config.REPO_ROOT).glob("*.sql"))
    assert paths, "no data tests found in sql/tests/"
    con = duckdb.connect()
    for path in paths:
        check.single_select(con, path.read_text(encoding="utf-8"), path.name)
