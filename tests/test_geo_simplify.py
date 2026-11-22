"""Simplification, topology checks and file output. Skipped without requirements-geo.txt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("shapely")
pytest.importorskip("pyproj")
pytest.importorskip("topojson")

import shapely  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402

from nl_housing import geo  # noqa: E402

from geo_fixtures import RoutedSession, grid_feature_collection, pages  # noqa: E402


@pytest.fixture(scope="module")
def small_fc() -> dict:
    """6 x 5 = 30 neighbours, enough to exercise shared borders quickly."""
    fc = grid_feature_collection(nx=6, ny=5)
    return geo.feature_collection(geo.select_properties(fc["features"]))


def _vertex_count(fc: dict) -> int:
    return sum(shapely.get_num_coordinates(shape(f["geometry"])) for f in fc["features"])


def test_shared_border_simplification_has_no_gaps_or_overlaps(small_fc):
    simplified = geo.simplify_shared_borders(small_fc, tolerance=150)
    report = geo.topology_check(small_fc, simplified)

    assert report.ok and report.new_holes == 0 and report.overlap_increase_m2 < 1
    assert _vertex_count(simplified) < 0.5 * _vertex_count(small_fc)
    assert [f["properties"] for f in simplified["features"]] == [f["properties"] for f in small_fc["features"]]
    assert all(set(f) == {"type", "properties", "geometry"} for f in simplified["features"])


def test_per_polygon_simplify_creates_slivers_and_is_rejected(small_fc):
    """Why topojson: simplifying each polygon on its own moves the two sides of a border differently."""
    naive = geo.feature_collection([
        {**f, "geometry": mapping(shape(f["geometry"]).simplify(150, preserve_topology=True))}
        for f in small_fc["features"]
    ])
    report = geo.topology_check(small_fc, naive)
    assert not report.ok
    assert report.overlap_increase_m2 > geo.MAX_OVERLAP_INCREASE_M2 or report.new_holes > 0


def test_zero_tolerance_is_a_no_op(small_fc):
    assert geo.simplify_shared_borders(small_fc, 0) is small_fc


def test_reproject_to_wgs84_and_round(small_fc):
    wgs84 = geo.reproject(small_fc, decimals=5)
    lon, lat = wgs84["features"][0]["geometry"]["coordinates"][0][0]
    assert 3.0 < lon < 7.5 and 50.5 < lat < 54.0  # inside the Netherlands
    assert round(lon, 5) == lon and round(lat, 5) == lat
    # Shared vertices stay shared after reprojection + rounding.
    assert geo.topology_check(geo.reproject(small_fc, dst="EPSG:28992", decimals=3), small_fc).ok


def test_topojson_text_is_quantized_and_keyed_on_statcode(small_fc):
    data = json.loads(geo.topojson_text(geo.reproject(small_fc)))
    assert data["type"] == "Topology" and "transform" in data
    geoms = data["objects"]["municipalities"]["geometries"]
    assert [g["id"] for g in geoms] == [f["properties"]["statcode"] for f in small_fc["features"]]
    assert set(geoms[0]["properties"]) == {"statcode", "statnaam"}

    plain = json.loads(geo.topojson_text(geo.reproject(small_fc), quantization=0))
    assert "transform" not in plain


def test_build_outputs_picks_smallest_tolerance_that_fits(small_fc):
    unsimplified = geo.build_outputs(small_fc, max_bytes=10**9, tolerances=(0,))
    budget = unsimplified.geojson_bytes // 2
    result = geo.build_outputs(small_fc, max_bytes=budget, tolerances=(0, 10, 50, 150, 300))
    assert result.tolerance_m > 0
    assert result.geojson_bytes < budget and result.topojson_bytes < budget
    assert result.topojson_bytes < result.geojson_bytes  # shared borders stored once
    assert result.report.ok and result.invalid_codes == []


def test_build_outputs_fails_when_nothing_fits(small_fc):
    with pytest.raises(geo.GeoValidationError, match="No tolerance"):
        geo.build_outputs(small_fc, max_bytes=100, tolerances=(0, 50))


def test_run_end_to_end_writes_files_to_tmp_path(tmp_path: Path):
    features = grid_feature_collection()["features"]  # 342 like the 2026 division
    session = RoutedSession(pages(features, page_size=1000))
    paths = geo.run(2026, root=tmp_path, session=session, max_bytes=geo.DEFAULT_MAX_BYTES)

    assert all(p.is_relative_to(tmp_path) and p.exists() for p in paths.values())
    out = json.loads(paths["geojson"].read_text())
    assert len(out["features"]) == 342
    assert {k for f in out["features"] for k in f["properties"]} == {"statcode", "statnaam"}
    assert paths["topojson"].stat().st_size < paths["geojson"].stat().st_size < geo.DEFAULT_MAX_BYTES

    meta = json.loads(paths["metadata"].read_text())
    assert meta["licence"] == "CC BY 4.0" and meta["feature_count"] == 342
    assert meta["query"] == {"f": "json", "jaarcode": 2026, "limit": 1000, "crs": geo.CRS_RD_NEW}
    assert meta["files"]["geojson"]["bytes"] == paths["geojson"].stat().st_size
    assert meta["files"]["geojson"]["path"] == "data/reference/municipalities_2026.geojson"
    assert meta["simplification"]["new_holes"] == 0
    assert not list(paths["geojson"].parent.glob(".*.tmp"))


def test_cli_passes_arguments_to_run(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(geo, "run", lambda **kw: calls.append(kw) or {})
    assert geo.main(["--year", "2026", "--tolerance", "50", "--force"]) == 0
    assert calls[0] == {"year": 2026, "force": True, "tolerance": 50.0,
                        "max_bytes": geo.DEFAULT_MAX_BYTES, "expected_count": None}


def test_cli_returns_1_on_validation_error(monkeypatch):
    def fail(**_):
        raise geo.GeoValidationError("expected 342 features, got 341")

    monkeypatch.setattr(geo, "run", fail)
    assert geo.main([]) == 1
