"""Synthetic municipality boundaries and fake PDOK responses for the geo tests (offline)."""

from __future__ import annotations

import math
from typing import Any

import requests

ITEMS_URL = "https://api.pdok.nl/cbs/gebiedsindelingen/ogc/v1/collections/gemeente_gegeneraliseerd/items"


def _edge_points(p: tuple[float, float], q: tuple[float, float], n: int, amplitude: float) -> list[tuple[float, float]]:
    """Wiggly line from p to q (excluding q). Computed in a canonical direction, so the two
    neighbours that share an edge get exactly the same vertices (like real CBS data)."""
    a, b = (p, q) if p <= q else (q, p)
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    pts = []
    for i in range(n):
        t = i / n
        off = amplitude * math.sin(7 * t * math.pi + a[0] / 997 + a[1] / 991) * math.sin(t * math.pi)
        pts.append((a[0] + dx * t + nx * off, a[1] + dy * t + ny * off))
    pts.append(b)
    if (p, q) != (a, b):
        pts.reverse()
    return pts[:-1]


def grid_feature_collection(
    nx: int = 18,
    ny: int = 19,
    cell_m: float = 5000.0,
    wiggles: int = 40,
    amplitude: float = 300.0,
    origin: tuple[float, float] = (120_000.0, 420_000.0),
    year: int | None = 2026,
) -> dict[str, Any]:
    """``nx * ny`` adjacent "municipalities" in RD New metres (default 342) with shared wiggly borders."""
    corners = {(i, j): (origin[0] + i * cell_m, origin[1] + j * cell_m) for i in range(nx + 1) for j in range(ny + 1)}
    features = []
    code = 1
    for j in range(ny):
        for i in range(nx):
            loop = [corners[(i, j)], corners[(i + 1, j)], corners[(i + 1, j + 1)], corners[(i, j + 1)]]
            ring: list[tuple[float, float]] = []
            for k in range(4):
                ring += _edge_points(loop[k], loop[(k + 1) % 4], wiggles, amplitude)
            # Start each ring at a different vertex, like real data (ring start points are arbitrary).
            shift = (code * 7) % len(ring)
            ring = ring[shift:] + ring[:shift]
            ring.append(ring[0])
            props: dict[str, Any] = {
                "statcode": f"GM{code:04d}",
                "statnaam": f"Gemeente {code}",
                "jrstatcode": f"2026GM{code:04d}",
                "rubriek": "gemeente",
                "startdatum": "2026-01-01T00:00:00Z",
                "einddatum": None,
            }
            if year is not None:
                props["jaarcode"] = year
            features.append(
                {
                    "type": "Feature",
                    "id": code,
                    "properties": props,
                    "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in ring]]},
                }
            )
            code += 1
    return {"type": "FeatureCollection", "features": features}


def pages(
    features: list[dict[str, Any]], page_size: int, base: str = ITEMS_URL, number_matched: bool = True
) -> dict[str, dict[str, Any]]:
    """Split features into OGC API pages keyed by URL; page 1 is the bare items URL."""
    chunks = [features[i : i + page_size] for i in range(0, len(features), page_size)] or [[]]
    urls = [base] + [f"{base}?f=json&jaarcode=2026&limit={page_size}&cursor=c{n}" for n in range(1, len(chunks))]
    routes = {}
    for n, (url, chunk) in enumerate(zip(urls, chunks, strict=True)):
        links = [{"rel": "self", "href": url}]
        if n + 1 < len(urls):
            links.append({"rel": "next", "type": "application/geo+json", "href": urls[n + 1]})
        page: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": chunk,
            "links": links,
            "numberReturned": len(chunk),
        }
        if number_matched:
            page["numberMatched"] = len(features)
        routes[url] = page
    return routes


class Response:
    def __init__(
        self, payload: dict[str, Any] | None = None, status: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self._payload = payload or {}
        self.status_code = status
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class RoutedSession:
    """Serves pages by URL and records ``(url, params)`` of every call."""

    def __init__(self, routes: dict[str, dict[str, Any]], headers: dict[str, str] | None = None) -> None:
        self.routes = routes
        self.headers = headers or {"Content-Crs": "<http://www.opengis.net/def/crs/EPSG/0/28992>"}
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> Response:
        self.calls.append((url, params))
        if url not in self.routes:
            return Response(status=404)
        return Response(self.routes[url], headers=self.headers)


class ScriptedSession:
    """Returns (or raises) the given items in order, one per call."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls = 0

    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> Response:
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
