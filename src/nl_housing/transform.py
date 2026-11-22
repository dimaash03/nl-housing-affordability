"""Run the SQL models in ``sql/`` against the local DuckDB file (review finding C2).

Each model is one file containing exactly one ``SELECT`` (CTEs allowed). The runner
wraps it as::

    CREATE OR REPLACE TABLE <layer>.<file stem> AS <select>

so every run rebuilds the tables from scratch (idempotent). The order of layers and
models is explicit in ``sql/models.yaml``::

    staging:
      - stg_cbs__house_prices
      - ...
    marts: []

Why an ordered list instead of numeric file prefixes or automatic dependency
parsing: file name = table name stays true (CLAUDE.md), the order is reviewable in
one place, and the project has only a handful of models, so a dbt-style DAG would
be more machinery than it saves. The runner checks that the list and the folder
match, so a new file cannot be forgotten.

All models run in one transaction: if any model fails, nothing is changed and the
previous tables stay in place.

Usage::

    python -m nl_housing.transform
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb
import yaml

from nl_housing import config

logger = logging.getLogger(__name__)

MODELS_FILE = "models.yaml"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class TransformError(RuntimeError):
    """Raised for an invalid model list or a model file that is not a single SELECT."""


@dataclass(frozen=True)
class Model:
    """One SQL model: ``sql/<layer>/<name>.sql`` -> table ``<layer>.<name>``."""

    layer: str
    name: str
    path: Path

    @property
    def table(self) -> str:
        return f"{self.layer}.{self.name}"


def sql_dir(root: Path = config.REPO_ROOT) -> Path:
    """Directory with the SQL layers and ``models.yaml``."""
    return root / "sql"


def _check_identifier(name: object, what: str) -> str:
    if not isinstance(name, str) or not _IDENTIFIER.match(name):
        raise TransformError(f"Invalid {what} name {name!r}: use lowercase snake_case")
    return name


def load_plan(root: Path = config.REPO_ROOT) -> dict[str, list[Model]]:
    """Read ``sql/models.yaml``: ``{layer: [models in execution order]}``, layers in file order.

    Raises :class:`TransformError` if a listed model has no file, a ``.sql`` file is
    not listed, or a name is listed twice.
    """
    base = sql_dir(root)
    models_path = base / MODELS_FILE
    if not models_path.exists():
        raise TransformError(f"Model list not found: {models_path}")
    data = yaml.safe_load(models_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise TransformError(f"{MODELS_FILE} must map layer names to lists of models")

    plan: dict[str, list[Model]] = {}
    seen: set[str] = set()
    for layer, names in data.items():
        layer = _check_identifier(layer, "layer")
        names = names or []
        if not isinstance(names, list):
            raise TransformError(f"Layer {layer!r} must be a list of model names")
        layer_dir = base / layer
        plan[layer] = []
        for name in names:
            name = _check_identifier(name, "model")
            if name in seen:
                raise TransformError(f"Model {name!r} is listed more than once")
            seen.add(name)
            path = layer_dir / f"{name}.sql"
            if not path.exists():
                raise TransformError(f"Model {layer}.{name} is listed but {path} does not exist")
            plan[layer].append(Model(layer=layer, name=name, path=path))
        on_disk = {p.stem for p in layer_dir.glob("*.sql")} if layer_dir.exists() else set()
        unlisted = sorted(on_disk - set(names))
        if unlisted:
            raise TransformError(f"SQL files in sql/{layer}/ not listed in {MODELS_FILE}: {unlisted}")
    return plan


def load_models(root: Path = config.REPO_ROOT) -> list[Model]:
    """All models in execution order (layers in file order, then models in listed order)."""
    return [model for models in load_plan(root).values() for model in models]


def model_select(con: duckdb.DuckDBPyConnection, model: Model) -> str:
    """Return the model's SQL after checking that it is exactly one SELECT statement."""
    text = model.path.read_text(encoding="utf-8")
    try:
        statements = con.extract_statements(text)
    except duckdb.Error as exc:
        raise TransformError(f"{model.path.name}: cannot parse SQL: {exc}") from exc
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        kinds = [s.type.name for s in statements]
        raise TransformError(f"{model.path.name}: expected exactly one SELECT statement, found {kinds}")
    # Drop a trailing semicolon so the text can be embedded in CREATE TABLE ... AS.
    return text.strip().rstrip(";")


def run(root: Path = config.REPO_ROOT, db_path: Path | None = None) -> dict[str, int]:
    """Build every model in order; return ``{table: row_count}``."""
    plan = load_plan(root)
    db_path = db_path or config.duckdb_path(root)
    if not db_path.exists():
        raise TransformError(f"DuckDB file not found: {db_path} - run `make load` first")

    counts: dict[str, int] = {}
    with duckdb.connect(str(db_path)) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            for layer in plan:  # also for empty layers, so downstream tools can rely on the schema
                con.execute(f"CREATE SCHEMA IF NOT EXISTS {layer}")
            for model in (m for models in plan.values() for m in models):
                select = model_select(con, model)
                # Newline before the SELECT: a trailing `-- comment` on the last line stays harmless.
                con.execute(f"CREATE OR REPLACE TABLE {model.table} AS\n{select}\n")
                counts[model.table] = con.execute(f"SELECT count(*) FROM {model.table}").fetchone()[0]
                logger.info("Built %s (%d rows)", model.table, counts[model.table])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    logger.info("Built %d model(s) in %s", len(counts), db_path.name)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the staging and marts SQL models in DuckDB.")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        run()
    except (TransformError, duckdb.Error) as exc:
        logger.error("Transform failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
