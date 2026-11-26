"""Export the ``marts`` schema to Parquet for Power BI and the website.

Power BI Desktop runs in a Windows VM without a DuckDB driver, so every mart table is written to
``data/processed/marts/<table>.parquet`` and imported with Power Query (see ``powerbi/README.md``).
Parquet keeps column types (integers, doubles, booleans), unlike CSV.

The export is idempotent: each file is overwritten, and files of tables that no longer exist in
``marts`` are removed so the folder always mirrors the database.

Usage::

    python -m nl_housing.export        # after `make transform`
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb

from nl_housing import config

logger = logging.getLogger(__name__)

SCHEMA = "marts"


@dataclass(frozen=True)
class ExportedTable:
    """One exported mart table."""

    table: str
    path: Path
    rows: int


def export_dir(root: Path = config.REPO_ROOT) -> Path:
    """Target folder of the Parquet files (``data/processed/marts``)."""
    return config.processed_dir(root) / SCHEMA


def mart_tables(con: duckdb.DuckDBPyConnection, schema: str = SCHEMA) -> list[str]:
    """Names of the base tables in ``schema``, sorted."""
    rows = con.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = ? and table_type = 'BASE TABLE'
        order by table_name
        """,
        [schema],
    ).fetchall()
    return [name for (name,) in rows]


def export(root: Path = config.REPO_ROOT, db_path: Path | None = None) -> list[ExportedTable]:
    """Write every ``marts`` table to Parquet; remove stale Parquet files. Returns what was written."""
    db_path = db_path or config.duckdb_path(root)
    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB file not found: {db_path} - run `make load transform` first")

    out_dir = export_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)

    exported: list[ExportedTable] = []
    with duckdb.connect(str(db_path), read_only=True) as con:
        tables = mart_tables(con)
        if not tables:
            raise RuntimeError(f"No tables in schema '{SCHEMA}' - run `make transform` first")
        for table in tables:
            path = out_dir / f"{table}.parquet"
            # Table names come from information_schema, the path from config; quoting guards both.
            con.execute(f"""copy "{SCHEMA}"."{table}" to '{path.as_posix()}' (format parquet)""")
            rows = con.execute(f'select count(*) from "{SCHEMA}"."{table}"').fetchone()[0]
            exported.append(ExportedTable(table=table, path=path, rows=rows))
            logger.info("Exported %s.%s -> %s (%d rows)", SCHEMA, table, path.relative_to(root), rows)

    keep = {t.path.name for t in exported}
    for stale in sorted(out_dir.glob("*.parquet")):
        if stale.name not in keep:
            stale.unlink()
            logger.info("Removed stale export %s", stale.relative_to(root))
    return exported


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the marts schema to data/processed/marts/*.parquet.")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        export()
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
