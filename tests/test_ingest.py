import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from nl_housing import ingest
from nl_housing.config import TableConfig

from conftest import TABLE_ID, FakeSession, make_routes


def test_urls():
    assert (
        ingest.api_url("83625NED", "DataProperties") == "https://opendata.cbs.nl/ODataApi/odata/83625NED/DataProperties"
    )
    assert ingest.feed_url("83625NED") == "https://opendata.cbs.nl/ODataFeed/odata/83625NED/TypedDataSet"
    assert ingest.api_url("X1", catalog="dataderden.cbs.nl").startswith("https://dataderden.cbs.nl/")


def test_fetch_all_follows_next_link():
    routes = make_routes()
    rows = ingest.fetch_all(ingest.feed_url(TABLE_ID), FakeSession(routes))
    assert [r["ID"] for r in rows] == [0, 1, 2]


def test_download_table_writes_expected_layout(repo_root: Path):
    session = FakeSession(make_routes())
    out = ingest.download_table(TableConfig(id=TABLE_ID, name="fake"), root=repo_root, session=session)

    assert out == repo_root / "data" / "raw" / TABLE_ID
    expected = {
        "typed_dataset.parquet",
        "data_properties.parquet",
        "table_infos.parquet",
        "dimensions/RegioS.parquet",
        "dimensions/Perioden.parquet",
        "metadata.json",
    }
    assert {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()} == expected
    assert not list(out.parent.glob(".*.tmp")), "temporary folder must be cleaned up"

    data = pd.read_parquet(out / "typed_dataset.parquet")
    assert len(data) == 3 and "RegioS" in data.columns  # codes kept, not labels
    assert set(data["RegioS"]) == {"GM0363", "GM0344", "NL01"}

    props = pd.read_parquet(out / "data_properties.parquet")
    assert not any(c.startswith("odata.") for c in props.columns)

    meta = json.loads((out / "metadata.json").read_text())
    assert meta["table_id"] == TABLE_ID
    assert meta["title"] == "Fake table"
    assert meta["row_count"] == 3
    assert meta["source_url"] == ingest.feed_url(TABLE_ID)
    assert meta["dimensions"] == ["RegioS", "Perioden"]
    assert meta["downloaded_at_utc"].endswith("+00:00")


def test_download_is_idempotent_and_force_redownloads(repo_root: Path):
    table = TableConfig(id=TABLE_ID)
    ingest.download_table(table, root=repo_root, session=FakeSession(make_routes()))

    second = FakeSession(make_routes())
    assert ingest.download_table(table, root=repo_root, session=second) is None
    assert second.calls == []  # no network when already downloaded

    forced = FakeSession(make_routes())
    assert ingest.download_table(table, root=repo_root, force=True, session=forced) is not None
    assert forced.calls


def test_failed_download_leaves_no_partial_output(repo_root: Path):
    routes = make_routes()
    del routes[f"https://opendata.cbs.nl/ODataFeed/odata/{TABLE_ID}/TypedDataSet"]
    with pytest.raises(requests.HTTPError):  # FakeSession answers 404 for the missing feed
        ingest.download_table(TableConfig(id=TABLE_ID), root=repo_root, session=FakeSession(routes))
    assert list((repo_root / "data" / "raw").iterdir()) == []
    assert not ingest.is_downloaded(TABLE_ID, repo_root)


def test_select_tables():
    tables = [TableConfig(id="11111NED"), TableConfig(id="22222NED", enabled=False)]
    assert [t.id for t in ingest.select_tables(tables, None)] == ["11111NED"]
    assert [t.id for t in ingest.select_tables(tables, "22222ned")] == ["22222NED"]  # explicit beats enabled
    assert [t.id for t in ingest.select_tables(tables, "33333NED")] == ["33333NED"]  # ad hoc


def test_run_reports_outcomes(repo_root: Path, write_config):
    write_config(f"tables:\n  - id: {TABLE_ID}\n  - id: 88888NED\n")
    result = ingest.run(root=repo_root, session=FakeSession(make_routes()))
    assert result == {"downloaded": [TABLE_ID], "skipped": [], "failed": ["88888NED"]}
