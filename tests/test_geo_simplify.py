"""Simplification, topology checks and file output. Skipped without requirements-geo.txt."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

if os.environ.get("NL_HOUSING_REQUIRE_GEO"):  # CI: a missing geo extra must fail, not skip
    import pyproj  # noqa: F401
    import shapely  # noqa: F401
    import topojson  # noqa: F401
else:
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
    naive = geo.feature_collection(
        [
            {**f, "geometry": mapping(shape(f["geometry"]).simplify(150, preserve_topology=True))}
            for f in small_fc["features"]
        ]
    )
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
    assert set(meta["output_checks"]) == {"geojson", "topojson"}
    assert all(c["new_holes"] == 0 for c in meta["output_checks"].values())
    assert not list(paths["geojson"].parent.glob(".*.tmp"))


def test_cli_passes_arguments_to_run(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(geo, "run", lambda **kw: calls.append(kw) or {})
    assert geo.main(["--year", "2026", "--tolerance", "50", "--force"]) == 0
    assert calls[0] == {
        "year": 2026,
        "force": True,
        "tolerance": 50.0,
        "max_bytes": geo.DEFAULT_MAX_BYTES,
        "expected_count": None,
    }


def test_cli_returns_1_on_validation_error(monkeypatch):
    def fail(**_):
        raise geo.GeoValidationError("expected 342 features, got 341")

    monkeypatch.setattr(geo, "run", fail)
    assert geo.main([]) == 1


# --- QA G-3: holes are matched one by one ----------------------------------------


def _square(x0: float, y0: float, size: float, code: str, hole: tuple[float, float, float] | None = None) -> dict:
    shell = [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]
    rings = [shell]
    if hole:
        hx, hy, hs = hole
        rings.append([[hx, hy], [hx, hy + hs], [hx + hs, hy + hs], [hx + hs, hy], [hx, hy]])
    return {
        "type": "Feature",
        "properties": {"statcode": code, "statnaam": code},
        "geometry": {"type": "Polygon", "coordinates": rings},
    }


def test_closing_one_hole_does_not_hide_a_new_gap():
    """Net hole count stays 1 -> 1, but the hole moved: one closed, one new gap -> not ok."""
    # Two 1 km squares side by side; a 100 m enclave hole inside the left one.
    original = geo.feature_collection(
        [_square(0, 0, 1000, "GM0001", hole=(200, 200, 100)), _square(1000, 0, 1000, "GM0002")]
    )
    # "Simplified": the enclave is filled, and the right square has a new 100 m hole (a gap).
    simplified = geo.feature_collection(
        [_square(0, 0, 1000, "GM0001"), _square(1000, 0, 1000, "GM0002", hole=(1500, 500, 100))]
    )
    report = geo.topology_check(original, simplified)
    assert report.holes_before == report.holes_after == 1
    assert report.new_holes == 1 and report.closed_holes == 1
    assert not report.ok


def test_hole_that_only_changes_shape_is_not_new():
    original = geo.feature_collection([_square(0, 0, 1000, "GM0001", hole=(200, 200, 100))])
    shifted = geo.feature_collection([_square(0, 0, 1000, "GM0001", hole=(210, 200, 100))])
    report = geo.topology_check(original, shifted)
    assert report.new_holes == 0 and report.closed_holes == 0 and report.ok


# --- QA G-4: the written files are checked after rounding ------------------------


def test_decoded_topojson_matches_the_geojson(small_fc):
    wgs84 = geo.reproject(geo.simplify_shared_borders(small_fc, 50))
    decoded = geo.decode_topojson(geo.topojson_text(wgs84))
    assert [f["properties"]["statcode"] for f in decoded["features"]] == [
        f["properties"]["statcode"] for f in wgs84["features"]
    ]
    for a, b in zip(decoded["features"], wgs84["features"], strict=True):
        ga, gb = shape(a["geometry"]), shape(b["geometry"])
        assert ga.is_valid
        # Quantization grid ~0.3 m: along a ~20 km perimeter that moves < 0.01 % of the area.
        assert ga.symmetric_difference(gb).area < 1e-4 * gb.area
    report, problems = geo.check_output(decoded, small_fc, "TopoJSON")
    assert problems == [] and report.ok


def test_check_output_flags_invalid_and_missing_features(small_fc):
    wgs84 = geo.reproject(small_fc)
    bowtie = copy.deepcopy(wgs84)
    ring = [list(p) for p in bowtie["features"][0]["geometry"]["coordinates"][0]]
    ring[1], ring[2] = ring[2], ring[1]  # self-intersecting ring
    bowtie["features"][0]["geometry"] = {"type": "Polygon", "coordinates": [ring]}
    _, problems = geo.check_output(bowtie, small_fc, "GeoJSON")
    assert any("invalid geometr" in p and "GM0001" in p for p in problems)

    dropped = geo.feature_collection(wgs84["features"][1:])
    _, problems = geo.check_output(dropped, small_fc, "GeoJSON")
    assert problems and "GM0001" in problems[0]


def test_build_outputs_skips_a_tolerance_whose_rounded_output_is_invalid(small_fc, monkeypatch):
    real = geo.check_output
    calls: list[float] = []

    def fail_first_tolerance(fc, fc_rd, label):
        report, problems = real(fc, fc_rd, label)
        calls.append(label)
        return report, (problems + ["forced"]) if len(calls) <= 2 else problems

    monkeypatch.setattr(geo, "check_output", fail_first_tolerance)
    result = geo.build_outputs(small_fc, max_bytes=10**9, tolerances=(10, 50))
    assert result.tolerance_m == 50
    assert set(result.output_reports) == {"geojson", "topojson"}

    monkeypatch.setattr(geo, "check_output", lambda fc, fc_rd, label: (real(fc, fc_rd, label)[0], ["broken"]))
    with pytest.raises(geo.GeoValidationError, match="Rejected after rounding"):
        geo.build_outputs(small_fc, max_bytes=10**9, tolerances=(10,))
