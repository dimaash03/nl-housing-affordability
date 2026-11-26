"""Download, pagination, retry, validation and property filtering (no geo dependencies needed)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import requests

from nl_housing import geo

from geo_fixtures import ITEMS_URL, Response, RoutedSession, ScriptedSession, grid_feature_collection, pages


@pytest.fixture(scope="module")
def features() -> list[dict]:
    return grid_feature_collection()["features"]


def no_sleep(_: float) -> None:
    pass


# --- Pagination ---------------------------------------------------------------


def test_items_url():
    assert geo.items_url() == ITEMS_URL


def test_fetch_follows_next_links(features):
    session = RoutedSession(pages(features, page_size=100))
    download = geo.fetch_features(2026, session=session, page_size=100)

    assert len(download.features) == 342 and download.pages == 4
    assert [f["properties"]["statcode"] for f in download.features] == [f"GM{i:04d}" for i in range(1, 343)]
    first_url, first_params = session.calls[0]
    assert first_url == ITEMS_URL
    assert first_params == {"f": "json", "jaarcode": 2026, "limit": 100, "crs": geo.CRS_RD_NEW}
    # Later pages use the next link verbatim (cursor + filters already inside it).
    assert all(params is None for _, params in session.calls[1:])
    assert "cursor=c3" in session.calls[-1][0]


def test_fetch_single_page_without_next_link(features):
    session = RoutedSession(pages(features, page_size=1000, number_matched=False))
    download = geo.fetch_features(2026, session=session)
    assert download.pages == 1 and len(download.features) == 342


@pytest.mark.parametrize("size", [0, 1001])
def test_fetch_rejects_page_size_outside_api_limits(size):
    with pytest.raises(ValueError, match="page_size"):
        geo.fetch_features(2026, session=RoutedSession({}), page_size=size)


def test_fetch_detects_pagination_loop(features):
    routes = pages(features[:4], page_size=2)
    second = next(url for url in routes if url != ITEMS_URL)
    routes[second]["links"].append({"rel": "next", "href": second})  # points to itself
    with pytest.raises(geo.GeoValidationError, match="loop"):
        geo.fetch_features(2026, session=RoutedSession(routes), page_size=2)


def test_fetch_checks_number_matched(features):
    routes = pages(features[:10], page_size=5)
    for page in routes.values():
        page["numberMatched"] = 11
    with pytest.raises(geo.GeoValidationError, match="numberMatched"):
        geo.fetch_features(2026, session=RoutedSession(routes), page_size=5)


def test_fetch_checks_content_crs(features):
    session = RoutedSession(
        pages(features[:3], page_size=10), headers={"Content-Crs": "<http://www.opengis.net/def/crs/OGC/1.3/CRS84>"}
    )
    with pytest.raises(geo.GeoValidationError, match="Content-Crs"):
        geo.fetch_features(2026, session=session, page_size=10)


def test_fetch_checks_content_crs_on_every_page(features):
    """QA G-6: a wrong CRS on a middle page must fail even if the last page is right."""
    good = {"Content-Crs": "<http://www.opengis.net/def/crs/EPSG/0/28992>"}
    bad = {"Content-Crs": "<http://www.opengis.net/def/crs/OGC/1.3/CRS84>"}

    class PerPageCrs(RoutedSession):
        def get(self, url, params=None, timeout=None):
            resp = super().get(url, params, timeout)
            resp.headers = bad if len(self.calls) == 2 else good
            return resp

    with pytest.raises(geo.GeoValidationError, match="page 2 has Content-Crs"):
        geo.fetch_features(2026, session=PerPageCrs(pages(features, page_size=100)), page_size=100)


def test_crs_matching_ignores_scheme_but_not_code():
    assert geo._crs_matches(geo.CRS_RD_NEW, "<https://www.opengis.net/def/crs/EPSG/0/28992>")
    assert not geo._crs_matches(geo.CRS_RD_NEW, "<http://www.opengis.net/def/crs/EPSG/0/4326>")
    assert not geo._crs_matches(geo.CRS_RD_NEW, "<http://www.opengis.net/def/crs/OGC/1.3/CRS84>")


def test_fetch_rejects_non_feature_collection():
    session = RoutedSession({ITEMS_URL: {"type": "Feature"}})
    with pytest.raises(geo.GeoValidationError, match="FeatureCollection"):
        geo.fetch_features(2026, session=session)


# --- Retries ------------------------------------------------------------------


def test_get_json_retries_transient_errors():
    waits: list[float] = []
    session = ScriptedSession(
        [
            requests.ConnectionError("reset"),
            Response(status=503),
            Response(status=429, headers={"Retry-After": "7"}),
            Response({"ok": True}),
        ]
    )
    payload, _ = geo.get_json(session, ITEMS_URL, retries=4, backoff_s=1.0, sleep=waits.append)
    assert payload == {"ok": True} and session.calls == 4
    assert waits == [1.0, 2.0, 7.0]  # exponential backoff, Retry-After honoured


def test_get_json_does_not_retry_client_errors():
    session = ScriptedSession([Response(status=400), Response({"ok": True})])
    with pytest.raises(requests.HTTPError):
        geo.get_json(session, ITEMS_URL, sleep=no_sleep)
    assert session.calls == 1


def test_get_json_gives_up_after_retries():
    session = ScriptedSession([Response(status=502)] * 3)
    with pytest.raises(requests.HTTPError):
        geo.get_json(session, ITEMS_URL, retries=2, sleep=no_sleep)
    assert session.calls == 3


# --- Validation ---------------------------------------------------------------


def test_validate_accepts_342_unique_gm_codes(features):
    geo.validate_features(features, 2026)


def test_validate_wrong_count(features):
    with pytest.raises(geo.GeoValidationError, match="expected 342 features, got 341"):
        geo.validate_features(features[:-1], 2026)


def test_validate_duplicate_code(features):
    bad = copy.deepcopy(features)
    bad[1]["properties"]["statcode"] = bad[0]["properties"]["statcode"]
    with pytest.raises(geo.GeoValidationError, match="duplicate statcode.*GM0001"):
        geo.validate_features(bad, 2026)


def test_validate_reports_all_problems_at_once(features):
    bad = copy.deepcopy(features)
    bad[0]["properties"]["statcode"] = "PV27"
    bad[1]["properties"]["statnaam"] = " "
    bad[2]["geometry"] = {"type": "Point", "coordinates": [0, 0]}
    bad[3]["properties"]["jaarcode"] = 2025
    with pytest.raises(geo.GeoValidationError) as exc:
        geo.validate_features(bad, 2026)
    message = str(exc.value)
    for fragment in (
        "'PV27'",
        "missing statnaam for: GM0002",
        "non-polygon geometry for: GM0003",
        "jaarcode other than 2026: 2025",
    ):
        assert fragment in message


def test_validate_accepts_jaarcode_as_string(features):
    """QA G-2: PDOK may return jaarcode as "2026" (string); that must not fail the run."""
    as_text = copy.deepcopy(features)
    for f in as_text:
        f["properties"]["jaarcode"] = "2026"
    geo.validate_features(as_text, 2026)
    as_text[5]["properties"]["jaarcode"] = "2025"
    with pytest.raises(geo.GeoValidationError, match="jaarcode other than 2026: 2025"):
        geo.validate_features(as_text, 2026)


def test_validate_trims_padded_codes(features):
    padded = copy.deepcopy(features)
    padded[0]["properties"]["statcode"] = "GM0001  "
    geo.validate_features(padded, 2026)


def test_validate_unknown_year_skips_count_unless_given(features):
    geo.validate_features(features[:5], year=None)
    with pytest.raises(geo.GeoValidationError, match="expected 6"):
        geo.validate_features(features[:5], year=None, expected_count=6)


# --- Property filtering -------------------------------------------------------


def test_select_properties_keeps_only_code_name_and_geometry(features):
    raw = copy.deepcopy(features[0])
    raw["properties"]["statnaam"] = " Gemeente 1 "
    out = geo.select_properties([raw])[0]
    assert set(out) == {"type", "properties", "geometry"}  # feature id dropped
    assert out["properties"] == {"statcode": "GM0001", "statnaam": "Gemeente 1"}
    assert out["geometry"] == raw["geometry"]
    assert "jrstatcode" in raw["properties"], "input must not be mutated"


# --- Cache --------------------------------------------------------------------


def test_load_or_download_caches_raw(tmp_path: Path, features):
    session = RoutedSession(pages(features, page_size=1000))
    fc, provenance = geo.load_or_download(2026, root=tmp_path, session=session)
    cache = geo.raw_cache_path(2026, tmp_path)
    assert cache.exists() and cache.is_relative_to(tmp_path / "data" / "raw")
    assert provenance["query"]["jaarcode"] == 2026 and len(fc["features"]) == 342

    fc2, provenance2 = geo.load_or_download(2026, root=tmp_path, session=RoutedSession({}))
    assert len(fc2["features"]) == 342 and provenance2 == json.loads(cache.read_text())["provenance"]
    assert len(session.calls) == 1  # second call served from the cache


def test_invalid_download_is_not_cached(tmp_path: Path, features):
    session = RoutedSession(pages(features[:-1], page_size=1000))
    with pytest.raises(geo.GeoValidationError):
        geo.load_or_download(2026, root=tmp_path, session=session)
    assert not geo.raw_cache_path(2026, tmp_path).exists()


def test_output_paths(tmp_path: Path):
    paths = geo.output_paths(2026, tmp_path)
    assert paths["geojson"] == tmp_path / "data" / "reference" / "municipalities_2026.geojson"
    assert paths["topojson"].name == "municipalities_2026.topojson"
    assert paths["metadata"].name == "municipalities_2026.metadata.json"
