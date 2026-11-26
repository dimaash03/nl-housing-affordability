"""Generic, idempotent downloader for CBS StatLine tables (OData v3 API).

For every table in the config this writes::

    data/raw/<table_id>/
        typed_dataset.parquet        # the observations (dimension *codes*, typed measures)
        data_properties.parquet      # column definitions: dimensions, topics, units
        table_infos.parquet          # title, period, modified date, ...
        category_groups.parquet      # hierarchy of dimension categories (omitted if CBS returns none)
        dimensions/<Key>.parquet     # one code table per dimension (RegioS, Perioden, ...)
        metadata.json                # provenance: id, title, download time (UTC), row count, URLs

Why plain ``requests`` instead of ``cbsodata.get_data``: ``get_data`` replaces
dimension codes (e.g. ``GM0363``) with their labels (``Amsterdam``). For a
reproducible pipeline we keep the stable codes in the fact data and the labels in
separate dimension tables, which map 1:1 to the Power BI star schema.

Robustness: all requests go through :func:`build_session`, a ``requests.Session``
whose adapter retries transient failures (HTTP 429/500/502/503/504 and connection
errors) with exponential backoff and honours the ``Retry-After`` header. urllib3's
retry stops once the status line has arrived, so :func:`fetch_all` additionally
retries a page whose *body* breaks off or is not valid JSON (:data:`BODY_ERRORS`).
A single hiccup of the CBS API therefore no longer fails a whole table.

Idempotency: a table is skipped when its ``metadata.json`` already exists,
unless ``--force`` is given. Downloads are written to a temporary folder and
moved into place only when complete, so an interrupted run never leaves a
half-written table that looks finished.

Usage::

    python -m nl_housing.ingest                # all enabled tables in the config
    python -m nl_housing.ingest --table 83625NED
    python -m nl_housing.ingest --force        # re-download everything
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from nl_housing import config
from nl_housing.config import TableConfig

logger = logging.getLogger(__name__)

METADATA_FILE = "metadata.json"
DATASET_FILE = "typed_dataset.parquet"
DIMENSIONS_DIR = "dimensions"

#: Metadata resources fetched for every table (besides the dataset and dimensions).
META_RESOURCES: dict[str, str] = {
    "TableInfos": "table_infos.parquet",
    "DataProperties": "data_properties.parquet",
    "CategoryGroups": "category_groups.parquet",
}

#: DataProperties.Type values that have their own code table endpoint.
DIMENSION_TYPES = {"Dimension", "TimeDimension", "GeoDimension", "GeoDetail"}

REQUEST_TIMEOUT_S = 60

#: HTTP statuses worth retrying: rate limiting (429) and transient server/gateway errors.
RETRY_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)
#: Max retries per request; with backoff 1 s the waits are 0, 2, 4, 8, 16 s (urllib3 skips the first).
RETRY_TOTAL = 5
RETRY_BACKOFF_FACTOR = 1.0

#: Errors raised while reading or decoding a response *body* after a 200 status line
#: (connection cut off half-way through a page, truncated JSON). urllib3's ``Retry`` does
#: not cover these, so :func:`fetch_all` retries the page itself.
BODY_ERRORS: tuple[type[Exception], ...] = (
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ContentDecodingError,
    requests.exceptions.JSONDecodeError,
)
#: Extra attempts per page for :data:`BODY_ERRORS`; waits BODY_BACKOFF_S * 2 ** n (2, 4, 8 s).
BODY_RETRIES = 3
BODY_BACKOFF_S = 2.0


# --- URLs --------------------------------------------------------------------


def api_url(table_id: str, resource: str = "", catalog: str = config.DEFAULT_CATALOG) -> str:
    """URL of a metadata resource (``ODataApi``), e.g. ``.../83625NED/DataProperties``."""
    base = f"https://{catalog}/ODataApi/odata/{table_id}"
    return f"{base}/{resource}" if resource else base


def feed_url(table_id: str, resource: str = "TypedDataSet", catalog: str = config.DEFAULT_CATALOG) -> str:
    """URL of the bulk feed (``ODataFeed``), which has no 10k-row cap per request."""
    return f"https://{catalog}/ODataFeed/odata/{table_id}/{resource}"


def statline_url(table_id: str) -> str:
    """Human-readable StatLine page for the table (for documentation/provenance)."""
    return f"https://opendata.cbs.nl/statline/#/CBS/nl/dataset/{table_id}/table"


# --- HTTP --------------------------------------------------------------------


def build_session(
    total: int = RETRY_TOTAL,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
) -> requests.Session:
    """Return a ``requests.Session`` that retries transient CBS API failures.

    - retries connection/read errors and the statuses in :data:`RETRY_STATUSES`;
    - waits ``backoff_factor * 2 ** (retry - 1)`` seconds between attempts (exponential backoff);
    - if the server sends ``Retry-After`` (typical for 429/503), that wait is used instead;
    - only idempotent methods are retried (the pipeline only issues GETs).

    When all retries are used up the last response is returned (``raise_on_status=False``),
    so :func:`fetch_all` still raises an ``HTTPError`` that names the status code.
    """
    retry = Retry(
        total=total,
        backoff_factor=backoff_factor,
        status_forcelist=RETRY_STATUSES,
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_page(session: requests.Session, url: str, params: dict[str, str] | None) -> dict[str, Any]:
    """GET one page and decode it, retrying :data:`BODY_ERRORS` with exponential backoff.

    HTTP errors are not retried here: the session's adapter already retried the
    transient ones, so ``raise_for_status()`` reports a final status.
    """
    for attempt in range(BODY_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json()
        except BODY_ERRORS as exc:
            if attempt == BODY_RETRIES:
                raise
            wait = BODY_BACKOFF_S * 2**attempt
            logger.warning(
                "Broken response body (%s) from %s; retry %d/%d in %.0f s",
                type(exc).__name__,
                url,
                attempt + 1,
                BODY_RETRIES,
                wait,
            )
            time.sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def fetch_all(url: str, session: requests.Session) -> list[dict[str, Any]]:
    """GET an OData collection as JSON, following ``odata.nextLink`` pagination."""
    rows: list[dict[str, Any]] = []
    next_url: str | None = url
    params: dict[str, str] | None = {"$format": "json"}
    while next_url:
        payload = _get_page(session, next_url, params)
        rows.extend(payload.get("value", []))
        next_url = payload.get("odata.nextLink")
        params = None  # nextLink already carries the query string
    return rows


def _write_parquet(df: pd.DataFrame, path: Path) -> bool:
    """Write ``df`` to parquet. Frames without columns (e.g. an empty
    CategoryGroups resource) are skipped: such a file cannot be read by DuckDB."""
    if df.shape[1] == 0:
        logger.debug("Skipping %s: no columns", path.name)
        return False
    df.to_parquet(path, index=False)
    return True


def _to_frame(rows: list[dict[str, Any]], stringify_objects: bool = False) -> pd.DataFrame:
    """Build a DataFrame; drop OData annotations; optionally cast object columns to string.

    Metadata tables mix types within a column (e.g. ``Default`` or ``Decimals``),
    which pyarrow cannot store, so they are stringified. The dataset itself keeps
    its native types.
    """
    df = pd.DataFrame(rows)
    df = df.drop(columns=[c for c in df.columns if c.startswith("odata.")], errors="ignore")
    if stringify_objects:
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype("string")
    return df


# --- Core --------------------------------------------------------------------


def is_downloaded(table_id: str, root: Path = config.REPO_ROOT) -> bool:
    """True if a complete download (with ``metadata.json``) already exists."""
    return (config.raw_table_dir(table_id, root) / METADATA_FILE).exists()


def download_table(
    table: TableConfig,
    root: Path = config.REPO_ROOT,
    force: bool = False,
    session: requests.Session | None = None,
) -> Path | None:
    """Download one CBS table into ``data/raw/<table_id>/``.

    Returns the output directory, or ``None`` if the table was skipped because it
    is already present and ``force`` is False.
    """
    out_dir = config.raw_table_dir(table.id, root)
    if is_downloaded(table.id, root) and not force:
        logger.info("[%s] already downloaded, skipping (use --force to refresh)", table.id)
        return None

    session = session or build_session()
    tmp_dir = out_dir.with_name(f".{table.id}.tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    (tmp_dir / DIMENSIONS_DIR).mkdir(parents=True)

    try:
        # 1) Metadata resources
        meta: dict[str, pd.DataFrame] = {}
        for resource, filename in META_RESOURCES.items():
            df = _to_frame(fetch_all(api_url(table.id, resource, table.catalog), session), stringify_objects=True)
            _write_parquet(df, tmp_dir / filename)
            meta[resource] = df
        title = _first_value(meta["TableInfos"], "Title")
        logger.info("[%s] %s", table.id, title or "(no title)")

        # 2) Dimension code tables (codes -> labels, e.g. GM0363 -> Amsterdam)
        props = meta["DataProperties"]
        dim_keys: list[str] = []
        if {"Type", "Key"} <= set(props.columns):
            dim_keys = props.loc[props["Type"].isin(DIMENSION_TYPES), "Key"].dropna().astype(str).tolist()
        for key in dim_keys:
            df = _to_frame(fetch_all(api_url(table.id, key, table.catalog), session), stringify_objects=True)
            _write_parquet(df, tmp_dir / DIMENSIONS_DIR / f"{key}.parquet")
            logger.info("[%s] dimension %s: %d codes", table.id, key, len(df))

        # 3) The observations
        source_url = feed_url(table.id, "TypedDataSet", table.catalog)
        data = _to_frame(fetch_all(source_url, session))
        data.to_parquet(tmp_dir / DATASET_FILE, index=False)
        logger.info("[%s] TypedDataSet: %d rows x %d cols", table.id, len(data), data.shape[1])

        # 4) Provenance (written last: its presence marks a complete download)
        metadata = {
            "table_id": table.id,
            "title": title,
            "config_name": table.name,
            "catalog": table.catalog,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "row_count": int(len(data)),
            "column_count": int(data.shape[1]),
            "source_url": source_url,
            "metadata_url": api_url(table.id, catalog=table.catalog),
            "statline_url": statline_url(table.id),
            "cbs_period": _first_value(meta["TableInfos"], "Period"),
            "cbs_modified": _first_value(meta["TableInfos"], "Modified"),
            "dimensions": dim_keys,
            "files": sorted(p.relative_to(tmp_dir).as_posix() for p in tmp_dir.rglob("*.parquet")),
        }
        (tmp_dir / METADATA_FILE).write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if out_dir.exists():
        shutil.rmtree(out_dir)
    tmp_dir.rename(out_dir)
    return out_dir


def _first_value(df: pd.DataFrame, column: str) -> str | None:
    if column in df.columns and len(df):
        value = df[column].iloc[0]
        return None if pd.isna(value) else str(value)
    return None


def select_tables(tables: list[TableConfig], table_id: str | None) -> list[TableConfig]:
    """Pick the tables to download: one by id (case-insensitive), or all enabled ones.

    An id that is not in the config is still allowed (ad-hoc exploration), with a warning.
    """
    if table_id is None:
        return [t for t in tables if t.enabled]
    config.validate_table_id(table_id)
    matches = [t for t in tables if t.id.lower() == table_id.lower()]
    if matches:
        return matches
    logger.warning("Table %s is not in the config; downloading it ad hoc", table_id)
    return [TableConfig(id=table_id)]


def run(
    table_id: str | None = None,
    force: bool = False,
    root: Path = config.REPO_ROOT,
    session: requests.Session | None = None,
) -> dict[str, list[str]]:
    """Download the selected tables. Returns ids grouped by outcome."""
    tables = select_tables(config.load_tables_config(root=root), table_id)
    result: dict[str, list[str]] = {"downloaded": [], "skipped": [], "failed": []}
    session = session or build_session()
    for table in tables:
        try:
            out = download_table(table, root=root, force=force, session=session)
            result["downloaded" if out else "skipped"].append(table.id)
        except (requests.RequestException, ValueError, OSError) as exc:
            logger.error("[%s] download failed: %s", table.id, exc)
            result["failed"].append(table.id)
    logger.info("Done. downloaded=%s skipped=%s failed=%s", result["downloaded"], result["skipped"], result["failed"])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download CBS StatLine tables into data/raw/.")
    parser.add_argument("--table", metavar="ID", help="download only this table id (e.g. 83625NED)")
    parser.add_argument("--force", action="store_true", help="re-download even if already present")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run(table_id=args.table, force=args.force)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
