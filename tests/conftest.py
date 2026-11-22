"""Shared fixtures. All tests run offline: HTTP is served by :class:`FakeSession`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

TABLE_ID = "99999NED"


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Minimal stand-in for ``requests.Session`` routing URLs to canned payloads."""

    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> FakeResponse:
        self.calls.append(url)
        if url not in self.routes:
            return FakeResponse({}, status=404)
        return FakeResponse(self.routes[url])


def make_routes(table_id: str = TABLE_ID) -> dict[str, dict[str, Any]]:
    api = f"https://opendata.cbs.nl/ODataApi/odata/{table_id}"
    feed = f"https://opendata.cbs.nl/ODataFeed/odata/{table_id}"
    page2 = f"{feed}/TypedDataSet?$format=json&$skip=2"
    return {
        f"{api}/TableInfos": {
            "value": [{"ID": 0, "Title": "Fake table", "Period": "2015-2024", "Modified": "2026-01-01T00:00:00"}]
        },
        f"{api}/DataProperties": {
            "value": [
                {
                    "odata.type": "Cbs.OData.GeoDimension",
                    "ID": 0,
                    "Type": "GeoDimension",
                    "Key": "RegioS",
                    "Decimals": None,
                },
                {
                    "odata.type": "Cbs.OData.TimeDimension",
                    "ID": 1,
                    "Type": "TimeDimension",
                    "Key": "Perioden",
                    "Decimals": None,
                },
                {"odata.type": "Cbs.OData.Topic", "ID": 2, "Type": "Topic", "Key": "Price_1", "Decimals": 0},
            ]
        },
        f"{api}/CategoryGroups": {"value": []},
        f"{api}/RegioS": {"value": [{"Key": "GM0363", "Title": "Amsterdam"}, {"Key": "GM0344", "Title": "Utrecht"}]},
        f"{api}/Perioden": {"value": [{"Key": "2024JJ00", "Title": "2024"}]},
        f"{feed}/TypedDataSet": {
            "value": [
                {"ID": 0, "RegioS": "GM0363", "Perioden": "2024JJ00", "Price_1": 1.0},
                {"ID": 1, "RegioS": "GM0344", "Perioden": "2024JJ00", "Price_1": 2.0},
            ],
            "odata.nextLink": page2,
        },
        page2: {"value": [{"ID": 2, "RegioS": "NL01", "Perioden": "2024JJ00", "Price_1": None}]},
    }


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A throwaway repo root with a config/ dir and an empty data/raw/."""
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "raw").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def write_config(repo_root: Path):
    def _write(text: str, name: str = "cbs_tables.yaml") -> Path:
        path = repo_root / "config" / name
        path.write_text(text, encoding="utf-8")
        return path

    return _write
