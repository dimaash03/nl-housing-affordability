"""Data tests: SQL assertions against the built DuckDB file (review finding C3).

Every file in ``sql/tests/`` is one ``SELECT`` that returns the rows that **violate**
an expectation (the dbt "singular test" convention):

- 0 rows  -> PASS
- >0 rows -> FAIL; the first rows are logged so the problem is visible at once.

Writing the expectation as "show me the bad rows" keeps each test readable as plain
SQL, and the output of a failing test is already the start of the investigation.

Usage::

    python -m nl_housing.check          # after `make transform`; exit code 1 on any failure
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from nl_housing import config
from nl_housing.transform import TransformError, single_select

logger = logging.getLogger(__name__)

TESTS_DIR_NAME = "tests"
MAX_ROWS_SHOWN = 10


@dataclass
class CheckResult:
    """Outcome of one SQL assertion."""

    name: str
    failing_rows: int
    columns: list[str] = field(default_factory=list)
    sample: list[tuple] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and self.failing_rows == 0


def tests_dir(root: Path = config.REPO_ROOT) -> Path:
    """Folder with the SQL assertions (``sql/tests``)."""
    return root / "sql" / TESTS_DIR_NAME


def run_check(con: duckdb.DuckDBPyConnection, path: Path) -> CheckResult:
    """Run one assertion file; SQL errors are reported as a failed check, not raised."""
    try:
        rel = con.sql(single_select(con, path.read_text(encoding="utf-8"), path.name))
        columns = list(rel.columns)
        rows = rel.fetchall()
    except (duckdb.Error, TransformError) as exc:
        return CheckResult(name=path.stem, failing_rows=0, error=str(exc))
    return CheckResult(name=path.stem, failing_rows=len(rows), columns=columns, sample=rows[:MAX_ROWS_SHOWN])


def run(root: Path = config.REPO_ROOT, db_path: Path | None = None) -> list[CheckResult]:
    """Run every ``sql/tests/*.sql`` file (alphabetical order) against the database (read-only)."""
    db_path = db_path or config.duckdb_path(root)
    if not db_path.exists():
        raise FileNotFoundError(f"DuckDB file not found: {db_path} - run `make load transform` first")
    paths = sorted(tests_dir(root).glob("*.sql"))
    with duckdb.connect(str(db_path), read_only=True) as con:
        results = [run_check(con, path) for path in paths]

    for r in results:
        if r.passed:
            logger.info("PASS %s", r.name)
        elif r.error:
            logger.error("ERROR %s: %s", r.name, r.error)
        else:
            logger.error("FAIL %s: %d failing row(s); columns %s", r.name, r.failing_rows, r.columns)
            for row in r.sample:
                logger.error("    %s", row)
    n_failed = sum(not r.passed for r in results)
    logger.info("%d check(s): %d passed, %d failed", len(results), len(results) - n_failed, n_failed)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SQL data tests in sql/tests/ against DuckDB.")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        results = run()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    return 0 if results and all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
