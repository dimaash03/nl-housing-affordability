"""Load everything in ``data/raw/`` into the local DuckDB file (schema ``raw``).

Naming (one set of tables per CBS table, ids lowercased and prefixed with ``cbs_``
because SQL identifiers must not start with a digit)::

    raw.cbs_83625ned                  <- typed_dataset.parquet (the observations)
    raw.cbs_83625ned__data_properties <- data_properties.parquet
    raw.cbs_83625ned__table_infos     <- table_infos.parquet
    raw.cbs_83625ned__category_groups <- category_groups.parquet
    raw.cbs_83625ned__dim_regios      <- dimensions/RegioS.parquet
    raw._ingest_log                   <- one row per table from metadata.json

Tables are recreated on every run (``CREATE OR REPLACE``), so loading is
idempotent. The raw layer is a faithful copy of CBS; all cleaning happens in
``sql/staging``.

Usage::

    python -m nl_housing.load_duckdb
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import duckdb

from nl_housing import config
from nl_housing.ingest import DATASET_FILE, DIMENSIONS_DIR, META_RESOURCES, METADATA_FILE

logger = logging.getLogger(__name__)

RAW_SCHEMA = "raw"
INGEST_LOG_TABLE = "_ingest_log"


def _sanitize(name: str) -> str:
    """Lowercase and keep only ``[a-z0-9_]`` so the name is a safe SQL identifier."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower())


def raw_table_name(table_id: str, suffix: str | None = None) -> str:
    """DuckDB table name for a CBS table (and optionally one of its parts).

    >>> raw_table_name("83625NED")
    'cbs_83625ned'
    >>> raw_table_name("83625NED", "dim_RegioS")
    'cbs_83625ned__dim_regios'
    """
    base = f"cbs_{_sanitize(config.validate_table_id(table_id))}"
    return f"{base}__{_sanitize(suffix)}" if suffix else base


def parquet_targets(table_dir: Path) -> dict[str, Path]:
    """Map DuckDB table names to the parquet files of one downloaded CBS table."""
    table_id = table_dir.name
    targets: dict[str, Path] = {}
    dataset = table_dir / DATASET_FILE
    if dataset.exists():
        targets[raw_table_name(table_id)] = dataset
    for filename in META_RESOURCES.values():
        path = table_dir / filename
        if path.exists():
            targets[raw_table_name(table_id, Path(filename).stem)] = path
    for path in sorted((table_dir / DIMENSIONS_DIR).glob("*.parquet")):
        targets[raw_table_name(table_id, f"dim_{path.stem}")] = path
    return targets


def downloaded_table_dirs(root: Path = config.REPO_ROOT) -> list[Path]:
    """Complete downloads only (folders that contain ``metadata.json``)."""
    base = config.raw_dir(root)
    if not base.exists():
        return []
    return sorted(
        p for p in base.iterdir()
        if p.is_dir() and not p.name.startswith(".") and (p / METADATA_FILE).exists()
    )


def load_all(root: Path = config.REPO_ROOT, db_path: Path | None = None) -> list[str]:
    """Load every downloaded CBS table into ``raw``; return the created table names."""
    db_path = db_path or config.duckdb_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    table_dirs = downloaded_table_dirs(root)
    if not table_dirs:
        logger.warning("No downloaded tables in %s - run `make ingest` first", config.raw_dir(root))

    created: list[str] = []
    log_rows: list[dict] = []
    with duckdb.connect(str(db_path)) as con:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}")
        for table_dir in table_dirs:
            for name, path in parquet_targets(table_dir).items():
                con.execute(
                    f"CREATE OR REPLACE TABLE {RAW_SCHEMA}.{name} AS SELECT * FROM read_parquet(?)",
                    [str(path)],
                )
                n = con.execute(f"SELECT count(*) FROM {RAW_SCHEMA}.{name}").fetchone()[0]
                logger.info("Loaded %s.%s (%d rows)", RAW_SCHEMA, name, n)
                created.append(name)
            meta = json.loads((table_dir / METADATA_FILE).read_text(encoding="utf-8"))
            log_rows.append({k: meta.get(k) for k in
                             ("table_id", "title", "downloaded_at_utc", "row_count", "source_url", "cbs_modified")})

        con.execute(
            f"""CREATE OR REPLACE TABLE {RAW_SCHEMA}.{INGEST_LOG_TABLE} (
                table_id VARCHAR, title VARCHAR, downloaded_at_utc TIMESTAMPTZ,
                row_count BIGINT, source_url VARCHAR, cbs_modified VARCHAR)"""
        )
        for row in log_rows:
            con.execute(
                f"INSERT INTO {RAW_SCHEMA}.{INGEST_LOG_TABLE} VALUES (?, ?, ?, ?, ?, ?)",
                [row["table_id"], row["title"], row["downloaded_at_utc"], row["row_count"],
                 row["source_url"], row["cbs_modified"]],
            )
    logger.info("Loaded %d table(s) into %s", len(created), db_path.name)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load data/raw/ into DuckDB (schema raw).")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
