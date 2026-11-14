from pathlib import Path

import duckdb

from nl_housing import ingest, load_duckdb
from nl_housing.config import TableConfig

from conftest import TABLE_ID, FakeSession, make_routes


def test_raw_table_name():
    assert load_duckdb.raw_table_name("83625NED") == "cbs_83625ned"
    assert load_duckdb.raw_table_name("83625NED", "dim_RegioS") == "cbs_83625ned__dim_regios"


def test_parquet_targets(repo_root: Path):
    out = ingest.download_table(TableConfig(id=TABLE_ID), root=repo_root, session=FakeSession(make_routes()))
    targets = load_duckdb.parquet_targets(out)
    prefix = f"cbs_{TABLE_ID.lower()}"
    assert set(targets) == {
        prefix,
        f"{prefix}__table_infos",
        f"{prefix}__data_properties",
        f"{prefix}__dim_regios",
        f"{prefix}__dim_perioden",
    }
    assert targets[prefix].name == "typed_dataset.parquet"


def test_incomplete_downloads_are_ignored(repo_root: Path):
    (repo_root / "data" / "raw" / "12345NED").mkdir()  # no metadata.json
    (repo_root / "data" / "raw" / ".12345NED.tmp").mkdir()
    assert load_duckdb.downloaded_table_dirs(repo_root) == []


def test_load_all_creates_raw_tables(repo_root: Path):
    ingest.download_table(TableConfig(id=TABLE_ID), root=repo_root, session=FakeSession(make_routes()))
    db = repo_root / "data" / "test.duckdb"

    created = load_duckdb.load_all(root=repo_root, db_path=db)
    created_again = load_duckdb.load_all(root=repo_root, db_path=db)  # idempotent
    assert created == created_again

    with duckdb.connect(str(db), read_only=True) as con:
        n = con.execute(f"SELECT count(*) FROM raw.cbs_{TABLE_ID.lower()}").fetchone()[0]
        dims = con.execute(f"SELECT count(*) FROM raw.cbs_{TABLE_ID.lower()}__dim_regios").fetchone()[0]
        log = con.execute("SELECT table_id, row_count FROM raw._ingest_log").fetchall()
    assert n == 3 and dims == 2
    assert log == [(TABLE_ID, 3)]


def test_load_all_with_no_data(repo_root: Path):
    db = repo_root / "data" / "empty.duckdb"
    assert load_duckdb.load_all(root=repo_root, db_path=db) == []
    assert db.exists()
