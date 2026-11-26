"""Offline tests for nl_housing.export (a temporary DuckDB file, no CBS data)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nl_housing import config, export


def _make_db(root: Path, tables: dict[str, str]) -> Path:
    """Create data/nl_housing.duckdb under ``root`` with the given marts tables (name -> select)."""
    db_path = config.duckdb_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("create schema marts")
        con.execute("create schema staging")
        con.execute("create table staging.not_exported as select 1 as x")
        for name, sql in tables.items():
            con.execute(f"create table marts.{name} as {sql}")
    return db_path


def test_exports_every_mart_table_with_types(tmp_path: Path) -> None:
    _make_db(
        tmp_path,
        {
            "dim_year": "select * from (values (2011, false), (2025, true)) t(year, is_preliminary)",
            "fct_x": "select 'GM0363' as municipality_code, 2011 as year, 1.5::double as ratio",
        },
    )
    result = export.export(root=tmp_path)

    assert [t.table for t in result] == ["dim_year", "fct_x"]
    out = export.export_dir(tmp_path)
    assert sorted(p.name for p in out.glob("*.parquet")) == ["dim_year.parquet", "fct_x.parquet"]
    with duckdb.connect() as con:
        rows = con.execute(f"select * from '{(out / 'dim_year.parquet').as_posix()}' order by year").fetchall()
        types = con.execute(f"describe select * from '{(out / 'dim_year.parquet').as_posix()}'").fetchall()
    assert rows == [(2011, False), (2025, True)]
    assert [t[1] for t in types] == ["INTEGER", "BOOLEAN"]
    assert {t.table: t.rows for t in result} == {"dim_year": 2, "fct_x": 1}


def test_removes_stale_files_and_overwrites(tmp_path: Path) -> None:
    _make_db(tmp_path, {"fct_x": "select 1 as a"})
    out = export.export_dir(tmp_path)
    out.mkdir(parents=True)
    (out / "old_table.parquet").write_bytes(b"stale")

    export.export(root=tmp_path)
    export.export(root=tmp_path)  # second run overwrites without error

    assert sorted(p.name for p in out.glob("*.parquet")) == ["fct_x.parquet"]


def test_missing_database_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        export.export(root=tmp_path)


def test_empty_marts_schema_raises(tmp_path: Path) -> None:
    _make_db(tmp_path, {})
    with pytest.raises(RuntimeError):
        export.export(root=tmp_path)


def test_main_returns_error_code_without_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(export, "export", lambda: (_ for _ in ()).throw(FileNotFoundError("no db")))
    assert export.main([]) == 1
