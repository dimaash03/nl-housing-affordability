"""Municipality boundaries for maps: download, validate, simplify, export.

Source: PDOK OGC API Features, dataset "CBS Gebiedsindelingen 2016 t/m heden",
collection ``gemeente_gegeneraliseerd`` (the CBS *generalised* municipal
boundaries), filtered on ``jaarcode`` (the year of the municipal division).
Licence: CC BY 4.0 (stated on the API landing page and in its OpenAPI ``info``
block); attribution text is in :data:`ATTRIBUTION`.

Outputs (committable, small)::

    data/reference/municipalities_<year>.geojson        # WGS84, for Azure Maps / notebooks
    data/reference/municipalities_<year>.topojson       # WGS84, quantized, for the Power BI Shape map
    data/reference/municipalities_<year>.metadata.json  # provenance, tolerance, sizes, licence

Cache (gitignored)::

    data/raw/geo/gemeente_gegeneraliseerd_<year>_epsg28992.geojson   # full download, RD New

Pipeline and the reasons behind each step:

1. **Download in EPSG:28992 (RD New)**, the storage CRS of the dataset. Coordinates
   are in metres, so the simplification tolerance means something ("50 m") and
   is the same in every direction (in degrees, 1 deg longitude is ~40 % shorter
   than 1 deg latitude at 52 N). Paging follows the ``next`` link (cursor based;
   the API allows at most 1000 items per page).
2. **Validate**: expected number of features (342 for 2026, D-006), unique
   ``statcode``, every code shaped like ``GM0363``, polygon geometry.
3. **Keep only** ``statcode`` and ``statnaam`` (smaller files, no confusing extra keys).
4. **Topology-preserving simplification** with the ``topojson`` package: shared
   borders are stored once as arcs and each arc is simplified once, so two
   neighbours always keep exactly the same border (no gaps or slivers). Per-polygon
   ``shapely.simplify(preserve_topology=True)`` only keeps *each polygon* valid; it
   simplifies the two sides of a border independently, which creates gaps and
   overlaps between neighbours. :func:`topology_check` measures exactly that and
   fails the run if simplification introduced either.
5. **Pick the smallest tolerance** from a ladder (0, 10, 25 ... m) whose output is
   below the size target (2 MB), so the map stays as detailed as the budget allows.
6. **Reproject to WGS84** (EPSG:4326, lon/lat, required by GeoJSON RFC 7946 and by
   Power BI) and round to 5 decimals (~1 m), then build the TopoJSON from the same
   simplified coordinates.
7. **Check the files as written**: the GeoJSON and the decoded TopoJSON must have the
   same municipalities in the same order, valid geometries, and no new gaps/overlaps
   (projected back to RD New). Otherwise the next tolerance is tried.

Usage::

    python -m nl_housing.geo                    # year 2026, cached download if present
    python -m nl_housing.geo --year 2026 --force
    python -m nl_housing.geo --tolerance 50     # fixed tolerance in metres

Heavy dependencies (``shapely``, ``pyproj``, ``topojson``) are in
``requirements-geo.txt`` and imported lazily, so the download/validation helpers
(and their tests) work with the base requirements only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from nl_housing import config

logger = logging.getLogger(__name__)

# --- Source ------------------------------------------------------------------

PDOK_BASE_URL = "https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1"
COLLECTION = "gemeente_gegeneraliseerd"
DEFAULT_YEAR = 2026

CRS_RD_NEW = "http://www.opengis.net/def/crs/EPSG/0/28992"
#: Maximum ``limit`` per page according to the API's OpenAPI document (min 1, max 1000, default 10).
MAX_PAGE_SIZE = 1000

LICENCE = "CC BY 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
DATASET_TITLE = "CBS Gebiedsindelingen 2016 t/m heden"
DATASET_METADATA_URL = (
    "https://nationaalgeoregister.nl/geonetwork/srv/dut/catalog.search#/metadata/effe1ab0-073d-437c-af13-df5c5e07d6cd"
)
ATTRIBUTION = (
    "Municipal boundaries: CBS Gebiedsindelingen (Statistics Netherlands, via PDOK), "
    "licensed under CC BY 4.0; simplified for this project."
)

# --- Validation --------------------------------------------------------------

#: Number of municipalities per division year. Only years documented in the
#: decisions log are listed (D-006); for other years pass ``--expected-count``.
EXPECTED_FEATURE_COUNTS: dict[int, int] = {2026: 342}
GM_CODE_PATTERN = re.compile(r"^GM\d{4}$")
KEEP_PROPERTIES: tuple[str, ...] = ("statcode", "statnaam")
POLYGON_TYPES = {"Polygon", "MultiPolygon"}

# --- Simplification / output -------------------------------------------------

DEFAULT_MAX_BYTES = 2_000_000  # "< 2 MB" target from D-014 (decimal MB, the stricter reading)
#: Tolerances (metres, Douglas-Peucker on shared arcs) tried from detailed to coarse.
DEFAULT_TOLERANCES_M: tuple[float, ...] = (0, 10, 25, 50, 75, 100, 150, 200, 300, 500)
COORD_DECIMALS = 5  # 1e-5 deg ~ 1.1 m north-south, ~0.7 m east-west at 52 N
TOPO_QUANTIZATION = 1_000_000  # TopoJSON grid: bbox / 1e6 ~ 0.3 m for NL
TOPO_OBJECT_NAME = "municipalities"

#: A run fails if simplification adds more overlap than this (m^2) or any new hole
#: larger than :data:`MIN_HOLE_AREA_M2` in the union of all municipalities.
MAX_OVERLAP_INCREASE_M2 = 1_000.0
MIN_HOLE_AREA_M2 = 1.0

REQUEST_TIMEOUT_S = 60
RETRY_STATUSES = {429, 500, 502, 503, 504}
USER_AGENT = "nl-housing-affordability/0.1 (python-requests)"


class GeoValidationError(ValueError):
    """Raised when downloaded or simplified boundaries fail a check."""


class GeoDependencyError(ImportError):
    """Raised when the optional geo dependencies are not installed."""


# --- Paths -------------------------------------------------------------------


def reference_dir(root: Path = config.REPO_ROOT) -> Path:
    """Committed reference data (``data/reference``)."""
    return root / "data" / "reference"


def output_paths(year: int, root: Path = config.REPO_ROOT) -> dict[str, Path]:
    """Paths of the three output files for ``year``."""
    base = reference_dir(root) / f"municipalities_{year}"
    return {
        "geojson": base.with_suffix(".geojson"),
        "topojson": base.with_suffix(".topojson"),
        "metadata": base.with_suffix(".metadata.json"),
    }


def raw_cache_path(year: int, root: Path = config.REPO_ROOT) -> Path:
    """Gitignored cache of the full-resolution download (RD New coordinates)."""
    return config.raw_dir(root) / "geo" / f"{COLLECTION}_{year}_epsg28992.geojson"


def items_url(collection: str = COLLECTION, base_url: str = PDOK_BASE_URL) -> str:
    """OGC API Features ``items`` endpoint of a collection."""
    return f"{base_url}/collections/{collection}/items"


# --- HTTP --------------------------------------------------------------------


def make_session() -> requests.Session:
    """A dedicated session for PDOK (separate from the CBS ingestion session)."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"})
    return session


def get_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any] | None = None,
    retries: int = 4,
    backoff_s: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], Any]:
    """GET ``url`` and return ``(json, response)``, retrying transient failures.

    Retries connection errors, timeouts and HTTP 429/5xx with exponential backoff
    (``backoff_s * 2**attempt``, or the server's ``Retry-After`` seconds if given).
    Other HTTP errors (e.g. 400 for a bad parameter) are raised immediately.
    """
    for attempt in range(retries + 1):
        last_attempt = attempt == retries
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if last_attempt:
                raise
            wait = backoff_s * 2**attempt
            logger.warning("%s on %s; retry %d/%d in %.0f s", type(exc).__name__, url, attempt + 1, retries, wait)
            sleep(wait)
            continue

        if resp.status_code in RETRY_STATUSES and not last_attempt:
            wait = _retry_after(resp) or backoff_s * 2**attempt
            logger.warning("HTTP %d on %s; retry %d/%d in %.0f s", resp.status_code, url, attempt + 1, retries, wait)
            sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json(), resp
    raise RuntimeError("unreachable")  # pragma: no cover


def _retry_after(resp: Any) -> float | None:
    value = (getattr(resp, "headers", None) or {}).get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:  # an HTTP date instead of seconds: fall back to backoff
        return None


_CRS_URI = re.compile(r"/crs/([^/]+)/[^/]+/([^/>\s]+)")


def _crs_matches(requested: str, content_crs: str) -> bool:
    """True if the ``Content-Crs`` header (``<uri>``) names the same authority and code as ``requested``.

    Compares ``EPSG`` + ``28992`` rather than the full URI, so ``http``/``https`` or a version
    segment do not matter, but ``OGC/1.3/CRS84`` never matches ``EPSG/0/28992``.
    """
    want, got = _CRS_URI.search(requested), _CRS_URI.search(content_crs)
    if not want or not got:
        return requested.rsplit("/", 1)[-1] in content_crs
    return (want.group(1).upper(), want.group(2)) == (got.group(1).upper(), got.group(2))


def _next_link(payload: dict[str, Any]) -> str | None:
    """``href`` of the ``rel="next"`` link (OGC API Features paging), if any."""
    for link in payload.get("links") or []:
        if link.get("rel") == "next" and link.get("href"):
            return str(link["href"])
    return None


@dataclass
class Download:
    """Result of :func:`fetch_features`."""

    features: list[dict[str, Any]]
    first_url: str
    params: dict[str, Any]
    pages: int
    number_matched: int | None = None
    content_crs: str | None = None
    downloaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


def fetch_features(
    year: int = DEFAULT_YEAR,
    session: requests.Session | None = None,
    page_size: int = MAX_PAGE_SIZE,
    crs: str = CRS_RD_NEW,
    max_pages: int = 100,
    sleep: Callable[[float], None] = time.sleep,
) -> Download:
    """Download every feature of ``gemeente_gegeneraliseerd`` for ``jaarcode=year``.

    The first request carries the query parameters; later pages use the ``next``
    link exactly as returned (it already holds the cursor and the filters).
    """
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}, got {page_size}")
    session = session or make_session()
    url = items_url()
    params: dict[str, Any] = {"f": "json", "jaarcode": year, "limit": page_size, "crs": crs}

    features: list[dict[str, Any]] = []
    seen_next: set[str] = set()
    next_url: str | None = url
    page_params: dict[str, Any] | None = params
    pages = 0
    number_matched: int | None = None
    content_crs: str | None = None

    while next_url:
        if pages >= max_pages:
            raise GeoValidationError(f"Stopped after {max_pages} pages; the API keeps returning 'next' links")
        payload, resp = get_json(session, next_url, params=page_params, sleep=sleep)
        pages += 1
        if payload.get("type") != "FeatureCollection":
            raise GeoValidationError(f"Page {pages} is not a GeoJSON FeatureCollection: type={payload.get('type')!r}")
        page_features = payload.get("features") or []
        features.extend(page_features)
        number_matched = payload.get("numberMatched", number_matched)
        page_crs = (getattr(resp, "headers", None) or {}).get("Content-Crs")
        if page_crs and not _crs_matches(crs, page_crs):  # checked per page (QA G-6)
            raise GeoValidationError(f"Requested CRS {crs} but page {pages} has Content-Crs {page_crs}")
        content_crs = page_crs or content_crs
        logger.info("Page %d: %d feature(s) (total %d)", pages, len(page_features), len(features))

        next_url = _next_link(payload)
        page_params = None  # the next link already carries the cursor and the filters
        if next_url in seen_next:
            raise GeoValidationError(f"Pagination loop: 'next' link repeats {next_url}")
        if next_url and not page_features:
            raise GeoValidationError(f"Page {pages} is empty but has a 'next' link")
        if next_url:
            seen_next.add(next_url)

    if number_matched is not None and number_matched != len(features):
        raise GeoValidationError(f"numberMatched={number_matched} but {len(features)} features were downloaded")
    logger.info("Downloaded %d feature(s) for jaarcode=%d in %d page(s)", len(features), year, pages)
    return Download(
        features=features,
        first_url=url,
        params=params,
        pages=pages,
        number_matched=number_matched,
        content_crs=content_crs,
    )


# --- Validation and property filtering ----------------------------------------


def _code(feature: dict[str, Any]) -> str:
    return str((feature.get("properties") or {}).get("statcode") or "").strip()


def validate_features(
    features: Sequence[dict[str, Any]],
    year: int | None = DEFAULT_YEAR,
    expected_count: int | None = None,
) -> None:
    """Raise :class:`GeoValidationError` listing every problem found.

    Checks: feature count (``expected_count``, else :data:`EXPECTED_FEATURE_COUNTS`),
    unique ``statcode``, ``GM`` + 4 digits, non-empty ``statnaam``, polygon geometry,
    and ``jaarcode == year`` where the property is present.
    """
    problems: list[str] = []
    if expected_count is None and year is not None:
        expected_count = EXPECTED_FEATURE_COUNTS.get(year)
        if expected_count is None:
            logger.warning("No expected feature count known for %s; count not checked", year)
    if expected_count is not None and len(features) != expected_count:
        problems.append(f"expected {expected_count} features, got {len(features)}")

    codes = [_code(f) for f in features]
    duplicates = sorted(c for c, n in Counter(codes).items() if n > 1)
    if duplicates:
        problems.append(f"duplicate statcode(s): {', '.join(duplicates[:10])}")
    bad_codes = sorted({c for c in codes if not GM_CODE_PATTERN.match(c)})
    if bad_codes:
        problems.append(f"statcode not shaped like 'GM0363': {', '.join(repr(c) for c in bad_codes[:10])}")

    pairs = list(zip(features, codes, strict=True))
    missing_names = [c for f, c in pairs if not str((f.get("properties") or {}).get("statnaam") or "").strip()]
    if missing_names:
        problems.append(f"missing statnaam for: {', '.join(missing_names[:10])}")

    bad_geom = [c for f, c in pairs if (f.get("geometry") or {}).get("type") not in POLYGON_TYPES]
    if bad_geom:
        problems.append(f"missing or non-polygon geometry for: {', '.join(bad_geom[:10])}")

    if year is not None:
        # Compare as text: the API may return jaarcode as a number (2026) or a string ("2026").
        wrong_year = sorted(
            {
                str(p.get("jaarcode")).strip()
                for f in features
                if "jaarcode" in (p := f.get("properties") or {}) and str(p.get("jaarcode")).strip() != str(year)
            }
        )
        if wrong_year:
            problems.append(f"jaarcode other than {year}: {', '.join(wrong_year)}")

    if problems:
        raise GeoValidationError("Boundary validation failed: " + "; ".join(problems))
    logger.info("Validation passed: %d municipalities, unique GM codes", len(features))


def select_properties(
    features: Iterable[dict[str, Any]], keep: Sequence[str] = KEEP_PROPERTIES
) -> list[dict[str, Any]]:
    """Return new features with only ``keep`` properties (string values trimmed) and the geometry.

    The feature ``id`` and other members are dropped: joins in Power BI use ``statcode``.
    """
    out = []
    for f in features:
        props = f.get("properties") or {}
        kept = {k: (v.strip() if isinstance(v, str) else v) for k, v in ((k, props.get(k)) for k in keep)}
        out.append({"type": "Feature", "properties": kept, "geometry": f.get("geometry")})
    return out


def feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


# --- Geometry (optional dependencies) -----------------------------------------


def _require_geo() -> tuple[Any, Any, Any]:
    """Import shapely, pyproj and topojson, with an actionable error if missing."""
    try:
        import pyproj
        import shapely
        import topojson
    except ImportError as exc:  # pragma: no cover - exercised only without the extras
        raise GeoDependencyError(
            "Geo dependencies missing: run `pip install -r requirements-geo.txt` in the project venv"
        ) from exc
    return shapely, pyproj, topojson


def simplify_shared_borders(fc: dict[str, Any], tolerance: float) -> dict[str, Any]:
    """Simplify a FeatureCollection so neighbouring polygons keep identical borders.

    ``tolerance`` is in the units of the coordinates (metres for RD New). With a
    tolerance of 0 the input is returned unchanged.
    """
    if tolerance <= 0:
        return fc
    _, _, topojson = _require_geo()
    topo = topojson.Topology(fc, prequantize=True, object_name=TOPO_OBJECT_NAME)
    simplified = topo.toposimplify(tolerance, prevent_oversimplify=True)
    out = json.loads(simplified.to_geojson())
    # topojson adds synthetic ids ("feature_0"); keep the property-only feature shape.
    for f in out["features"]:
        f.pop("id", None)
    return out


@dataclass(frozen=True)
class TopologyReport:
    """Gaps/overlaps between neighbours before vs after simplification (RD New, m^2).

    Holes are matched one by one (QA G-3): a hole of the simplified union is *new* if it
    does not overlap any hole of the original union, so closing an existing hole (an
    enclave, a lake outside every municipality) cannot hide a gap opened elsewhere.
    """

    overlap_before_m2: float
    overlap_after_m2: float
    holes_before: int
    holes_after: int
    max_area_change_pct: float
    max_area_change_code: str
    new_holes: int = 0
    closed_holes: int = 0

    @property
    def overlap_increase_m2(self) -> float:
        return self.overlap_after_m2 - self.overlap_before_m2

    @property
    def ok(self) -> bool:
        return self.overlap_increase_m2 <= MAX_OVERLAP_INCREASE_M2 and self.new_holes == 0


def _geometries(fc: dict[str, Any]) -> list[Any]:
    shapely, _, _ = _require_geo()
    from shapely.geometry import shape

    return [shapely.make_valid(shape(f["geometry"])) for f in fc["features"]]


def _overlap_and_holes(geoms: list[Any]) -> tuple[float, list[Any]]:
    """(sum of areas - area of union, interior rings of the union larger than MIN_HOLE_AREA_M2 as polygons)."""
    shapely, _, _ = _require_geo()
    from shapely.geometry import Polygon

    union = shapely.union_all(geoms)
    overlap = sum(g.area for g in geoms) - union.area
    polygons = [g for g in getattr(union, "geoms", [union]) if isinstance(g, Polygon)]
    holes = [h for p in polygons for ring in p.interiors if (h := Polygon(ring)).area > MIN_HOLE_AREA_M2]
    return max(overlap, 0.0), holes


def _unmatched(holes: list[Any], others: list[Any]) -> int:
    """Number of ``holes`` that share no area (> MIN_HOLE_AREA_M2) with any of ``others``."""
    shapely, _, _ = _require_geo()

    if not others:
        return len(holes)
    tree = shapely.STRtree(others)
    count = 0
    for hole in holes:
        candidates = [others[i] for i in tree.query(hole)]
        if not any(hole.intersection(o).area > MIN_HOLE_AREA_M2 for o in candidates):
            count += 1
    return count


def topology_check(original: dict[str, Any], simplified: dict[str, Any]) -> TopologyReport:
    """Compare overlaps and holes between neighbours before and after simplification.

    Gaps between neighbours show up as new interior rings ("holes") in the union of
    all municipalities; slivers where neighbours cross show up as extra overlap area
    (sum of areas minus area of the union). Both FeatureCollections must be in a
    projected CRS (metres) and in the same feature order.
    """
    before, after = _geometries(original), _geometries(simplified)
    if len(before) != len(after):
        raise GeoValidationError(f"Simplification changed the feature count: {len(before)} -> {len(after)}")
    overlap_before, holes_before = _overlap_and_holes(before)
    overlap_after, holes_after = _overlap_and_holes(after)
    new_holes = _unmatched(holes_after, holes_before)
    closed_holes = _unmatched(holes_before, holes_after)

    changes = [
        (abs(a.area - b.area) / b.area * 100 if b.area else 0.0, _code(f))
        for b, a, f in zip(before, after, original["features"], strict=True)
    ]
    max_change, max_code = max(changes, default=(0.0, ""))
    return TopologyReport(
        overlap_before,
        overlap_after,
        len(holes_before),
        len(holes_after),
        max_change,
        max_code,
        new_holes=new_holes,
        closed_holes=closed_holes,
    )


def reproject(
    fc: dict[str, Any], src: str = "EPSG:28992", dst: str = "EPSG:4326", decimals: int = COORD_DECIMALS
) -> dict[str, Any]:
    """Reproject every coordinate and round to ``decimals``.

    Shared vertices stay shared: the same input coordinate always maps to the same
    rounded output coordinate. Output order is lon, lat (``always_xy``).
    """
    shapely, pyproj, _ = _require_geo()
    from shapely.geometry import mapping, shape

    transformer = pyproj.Transformer.from_crs(src, dst, always_xy=True)

    import numpy as np  # installed with shapely

    def _transform(coords: Any) -> Any:
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.round(np.column_stack([x, y]), decimals)

    features = []
    for f in fc["features"]:
        geom = shapely.transform(shape(f["geometry"]), _transform)
        features.append({"type": "Feature", "properties": dict(f["properties"]), "geometry": mapping(geom)})
    return feature_collection(features)


def count_invalid(fc: dict[str, Any]) -> list[str]:
    """Codes of features whose geometry is not valid (reported, not repaired)."""
    shapely, _, _ = _require_geo()
    from shapely.geometry import shape

    return [_code(f) for f in fc["features"] if not shapely.is_valid(shape(f["geometry"]))]


def geojson_text(fc: dict[str, Any]) -> str:
    """Compact GeoJSON (no whitespace): the size budget counts every byte."""
    return json.dumps(fc, separators=(",", ":"), ensure_ascii=False)


def topojson_text(fc: dict[str, Any], quantization: float = TOPO_QUANTIZATION) -> str:
    """Quantized TopoJSON with one object ``municipalities``; geometry ``id`` = ``statcode``.

    Coordinates are already simplified; this step only builds the arcs, so no
    further simplification happens here. ``quantization=0`` writes plain coordinates.
    """
    _, _, topojson = _require_geo()
    topo = topojson.Topology(fc, prequantize=False, topoquantize=quantization or False, object_name=TOPO_OBJECT_NAME)
    data = json.loads(topo.to_json())
    for geom in data["objects"][TOPO_OBJECT_NAME]["geometries"]:
        geom["id"] = (geom.get("properties") or {}).get("statcode", geom.get("id"))
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def decode_topojson(text: str, object_name: str = TOPO_OBJECT_NAME) -> dict[str, Any]:
    """Decode a TopoJSON text back into a GeoJSON FeatureCollection (spec 1.0: delta-encoded arcs).

    Used to check the file that is actually written (QA G-4): what Power BI reads is the
    quantized TopoJSON, not the GeoJSON it was built from. Each feature gets
    ``properties["statcode"]`` from the geometry ``id`` if the properties lack it.
    """
    topo = json.loads(text)
    transform = topo.get("transform")
    sx, sy = transform["scale"] if transform else (1.0, 1.0)
    tx, ty = transform["translate"] if transform else (0.0, 0.0)

    arcs: list[list[list[float]]] = []
    for arc in topo["arcs"]:
        points, x, y = [], 0.0, 0.0
        for px, py, *_ in arc:
            if transform:
                x, y = x + px, y + py  # delta-encoded integers
                points.append([x * sx + tx, y * sy + ty])
            else:
                points.append([px, py])
        arcs.append(points)

    def ring(indexes: list[int]) -> list[list[float]]:
        coords: list[list[float]] = []
        for i in indexes:
            arc = arcs[i] if i >= 0 else arcs[~i][::-1]
            coords.extend(arc if not coords else arc[1:])  # consecutive arcs share their end point
        return coords

    features = []
    for g in topo["objects"][object_name]["geometries"]:
        if g.get("type") == "Polygon":
            geometry = {"type": "Polygon", "coordinates": [ring(r) for r in g["arcs"]]}
        elif g.get("type") == "MultiPolygon":
            geometry = {"type": "MultiPolygon", "coordinates": [[ring(r) for r in poly] for poly in g["arcs"]]}
        else:
            geometry = {"type": g.get("type"), "coordinates": []}
        props = dict(g.get("properties") or {})
        props.setdefault("statcode", g.get("id"))
        features.append({"type": "Feature", "properties": props, "geometry": geometry})
    return feature_collection(features)


def check_output(fc_wgs84: dict[str, Any], fc_rd: dict[str, Any], label: str) -> tuple[TopologyReport, list[str]]:
    """Validate a written output (after rounding / quantization) against the RD New source.

    Returns ``(topology report, problems)``. Problems: a different feature list or order,
    invalid geometries, or gaps/overlaps between neighbours after projecting the output
    back to RD New (so the thresholds stay in m^2).
    """
    problems: list[str] = []
    codes_out = [_code(f) for f in fc_wgs84["features"]]
    codes_src = [_code(f) for f in fc_rd["features"]]
    if codes_out != codes_src:
        missing = sorted(set(codes_src) - set(codes_out))[:10]
        problems.append(f"{label}: statcodes differ from the source (missing: {', '.join(missing) or 'none'})")
        return topology_check(fc_rd, fc_rd), problems  # geometries cannot be paired; report is not meaningful

    invalid = count_invalid(fc_wgs84)
    if invalid:
        problems.append(f"{label}: {len(invalid)} invalid geometr(y/ies): {', '.join(invalid[:10])}")
    report = topology_check(fc_rd, reproject(fc_wgs84, src="EPSG:4326", dst="EPSG:28992", decimals=3))
    if not report.ok:
        problems.append(
            f"{label}: gaps/overlaps after rounding (overlap +{report.overlap_increase_m2:.0f} m2, "
            f"new holes {report.new_holes})"
        )
    return report, problems


@dataclass
class BuildResult:
    geojson: str
    topojson: str
    tolerance_m: float
    report: TopologyReport
    invalid_codes: list[str]
    #: Checks of the written files themselves (after rounding / quantization), QA G-4.
    output_reports: dict[str, TopologyReport] = field(default_factory=dict)

    @property
    def geojson_bytes(self) -> int:
        return len(self.geojson.encode("utf-8"))

    @property
    def topojson_bytes(self) -> int:
        return len(self.topojson.encode("utf-8"))


def build_outputs(
    fc_rd: dict[str, Any],
    max_bytes: int = DEFAULT_MAX_BYTES,
    tolerances: Sequence[float] = DEFAULT_TOLERANCES_M,
    decimals: int = COORD_DECIMALS,
    quantization: float = TOPO_QUANTIZATION,
) -> BuildResult:
    """Try ``tolerances`` in order; return the first result whose GeoJSON and TopoJSON
    are both below ``max_bytes`` and that passes :func:`topology_check`.

    The simplified RD New geometry must pass the topology check (a failure there means
    the source does not share vertices, so a coarser tolerance would not help: raise).
    The two output files are then checked as written (:func:`check_output`): if rounding
    or quantization breaks them, the next tolerance is tried, and the run fails if none passes.
    """
    rejected: list[str] = []
    for tol in tolerances:
        t0 = time.perf_counter()
        simplified_rd = simplify_shared_borders(fc_rd, tol)
        report = topology_check(fc_rd, simplified_rd)
        wgs84 = reproject(simplified_rd, decimals=decimals)
        result = BuildResult(geojson_text(wgs84), topojson_text(wgs84, quantization), tol, report, count_invalid(wgs84))
        logger.info(
            "tolerance %g m: GeoJSON %s, TopoJSON %s, overlap +%.0f m2, new holes %d, max area change %.2f%% (%s) "
            "[%.1f s]",
            tol,
            _human(result.geojson_bytes),
            _human(result.topojson_bytes),
            report.overlap_increase_m2,
            report.new_holes,
            report.max_area_change_pct,
            report.max_area_change_code,
            time.perf_counter() - t0,
        )
        if not report.ok:
            raise GeoValidationError(
                f"Simplification at {tol} m created gaps/overlaps between neighbours "
                f"(overlap +{report.overlap_increase_m2:.0f} m2, new holes {report.new_holes}). "
                "Check that neighbouring polygons share identical vertices in the source."
            )
        if result.geojson_bytes >= max_bytes or result.topojson_bytes >= max_bytes:
            continue
        problems: list[str] = []
        for label, fc_out in (
            ("GeoJSON", json.loads(result.geojson)),
            ("TopoJSON", decode_topojson(result.topojson)),
        ):
            out_report, out_problems = check_output(fc_out, fc_rd, label)
            result.output_reports[label.lower()] = out_report
            problems.extend(out_problems)
        if problems:
            logger.warning("tolerance %g m rejected after rounding: %s", tol, "; ".join(problems))
            rejected.append(f"{tol} m: " + "; ".join(problems))
            continue
        return result
    detail = f" Rejected after rounding: {' | '.join(rejected)}" if rejected else ""
    raise GeoValidationError(
        f"No tolerance in {list(tolerances)} m gives valid files below {_human(max_bytes)}.{detail}"
    )


def _human(n_bytes: int) -> str:
    return f"{n_bytes / 1_000_000:.2f} MB" if n_bytes >= 100_000 else f"{n_bytes / 1000:.1f} kB"


# --- Orchestration -------------------------------------------------------------


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def load_or_download(
    year: int,
    root: Path = config.REPO_ROOT,
    force: bool = False,
    session: requests.Session | None = None,
    expected_count: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(feature_collection_rd, provenance)``; download only if the cache is missing or ``force``."""
    cache = raw_cache_path(year, root)
    if cache.exists() and not force:
        logger.info("Using cached download %s (use --force to re-download)", cache.relative_to(root))
        data = json.loads(cache.read_text(encoding="utf-8"))
        validate_features(data["features"], year, expected_count)
        return feature_collection(data["features"]), data["provenance"]

    download = fetch_features(year, session=session)
    validate_features(download.features, year, expected_count)
    provenance = {
        "source_url": download.first_url,
        "query": download.params,
        "pages": download.pages,
        "content_crs": download.content_crs,
        "downloaded_at_utc": download.downloaded_at,
    }
    _write_atomic(
        cache,
        json.dumps(
            {"type": "FeatureCollection", "provenance": provenance, "features": download.features},
            separators=(",", ":"),
        ),
    )
    logger.info("Cached full download: %s (%s)", cache.relative_to(root), _human(cache.stat().st_size))
    return feature_collection(download.features), provenance


def run(
    year: int = DEFAULT_YEAR,
    root: Path = config.REPO_ROOT,
    force: bool = False,
    tolerance: float | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    expected_count: int | None = None,
    session: requests.Session | None = None,
) -> dict[str, Path]:
    """Download (or reuse), validate, simplify and write the boundary files for ``year``."""
    fc_raw, provenance = load_or_download(year, root, force, session, expected_count)
    fc_rd = feature_collection(select_properties(fc_raw["features"]))

    tolerances = (tolerance,) if tolerance is not None else DEFAULT_TOLERANCES_M
    result = build_outputs(fc_rd, max_bytes=max_bytes, tolerances=tolerances)

    # Re-validate the output: simplification must not drop or rename municipalities.
    out_features = json.loads(result.geojson)["features"]
    validate_features(out_features, year, expected_count or len(fc_rd["features"]))

    paths = output_paths(year, root)
    _write_atomic(paths["geojson"], result.geojson)
    _write_atomic(paths["topojson"], result.topojson)
    metadata = {
        "dataset": DATASET_TITLE,
        "collection": COLLECTION,
        "jaarcode": year,
        **provenance,
        "dataset_metadata_url": DATASET_METADATA_URL,
        "licence": LICENCE,
        "licence_url": LICENCE_URL,
        "attribution": ATTRIBUTION,
        "feature_count": len(out_features),
        "properties": list(KEEP_PROPERTIES),
        "simplification": {
            "method": "topojson toposimplify (Douglas-Peucker on shared arcs) in EPSG:28992",
            "tolerance_m": result.tolerance_m,
            "overlap_increase_m2": round(result.report.overlap_increase_m2, 1),
            "new_holes": result.report.new_holes,
            "closed_holes": result.report.closed_holes,
            "max_area_change_pct": round(result.report.max_area_change_pct, 3),
            "max_area_change_statcode": result.report.max_area_change_code,
            "invalid_geometries": result.invalid_codes,
        },
        "output_checks": {
            kind: {
                "overlap_increase_m2": round(rep.overlap_increase_m2, 1),
                "new_holes": rep.new_holes,
                "max_area_change_pct": round(rep.max_area_change_pct, 3),
            }
            for kind, rep in result.output_reports.items()
        },
        "output_crs": "EPSG:4326 (lon, lat)",
        "coordinate_decimals": COORD_DECIMALS,
        "topojson_quantization": TOPO_QUANTIZATION,
        "files": {
            kind: {
                "path": paths[kind].relative_to(root).as_posix(),
                "bytes": paths[kind].stat().st_size,
                "sha256": hashlib.sha256(paths[kind].read_bytes()).hexdigest(),
            }
            for kind in ("geojson", "topojson")
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_atomic(paths["metadata"], json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    for kind in ("geojson", "topojson", "metadata"):
        logger.info("Wrote %s (%s)", paths[kind].relative_to(root), _human(paths[kind].stat().st_size))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download and simplify CBS municipality boundaries (PDOK).")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help="municipal division year (jaarcode)")
    parser.add_argument("--force", action="store_true", help="re-download even if the raw cache exists")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="fixed simplification tolerance in metres (default: smallest that fits)",
    )
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="size target per output file")
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help="expected number of municipalities (default: known value for the year)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        run(
            year=args.year,
            force=args.force,
            tolerance=args.tolerance,
            max_bytes=args.max_bytes,
            expected_count=args.expected_count,
        )
    except (GeoValidationError, GeoDependencyError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
