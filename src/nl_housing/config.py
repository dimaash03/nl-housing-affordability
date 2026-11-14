"""Project paths and CBS table configuration.

All paths are derived from the repository root, so the code works from any
working directory and on any machine (no absolute paths are hardcoded).

The table list lives in ``config/cbs_tables.yaml`` (maintained alongside the
data research). If that file does not exist yet, ``config/cbs_tables.example.yaml``
is used instead so the pipeline can still be smoke-tested.

Accepted YAML shapes (kept deliberately tolerant)::

    tables:                       # list of mappings (preferred)
      - id: 83625NED
        name: avg_sale_price_region
        description: ...
        enabled: true

    tables:                       # list of plain ids
      - 83625NED

    tables:                       # mapping keyed by id
      83625NED:
        name: avg_sale_price_region
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# --- Paths -------------------------------------------------------------------

#: Repository root: src/nl_housing/config.py -> parents[2]
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

CONFIG_DIR_NAME = "config"
TABLES_CONFIG_NAME = "cbs_tables.yaml"
TABLES_EXAMPLE_CONFIG_NAME = "cbs_tables.example.yaml"

DEFAULT_CATALOG = "opendata.cbs.nl"

_TABLE_ID_PATTERN = re.compile(r"^[0-9A-Za-z]+$")
_ID_KEYS = ("id", "table_id", "identifier")


def raw_dir(root: Path = REPO_ROOT) -> Path:
    """Directory holding raw CBS downloads (``data/raw``)."""
    return root / "data" / "raw"


def processed_dir(root: Path = REPO_ROOT) -> Path:
    """Directory for derived files, e.g. exported marts (``data/processed``)."""
    return root / "data" / "processed"


def duckdb_path(root: Path = REPO_ROOT) -> Path:
    """Location of the local DuckDB database file."""
    return root / "data" / "nl_housing.duckdb"


def raw_table_dir(table_id: str, root: Path = REPO_ROOT) -> Path:
    """Output directory for one CBS table: ``data/raw/<table_id>/``.

    The id is used exactly as written in the config (CBS ids are case-insensitive,
    but keeping the original spelling makes the folder easy to match to StatLine).
    """
    validate_table_id(table_id)
    return raw_dir(root) / table_id


# --- Table config ------------------------------------------------------------


class ConfigError(ValueError):
    """Raised when the CBS table configuration is missing or malformed."""


@dataclass(frozen=True)
class TableConfig:
    """One CBS StatLine table to ingest."""

    id: str
    name: str | None = None
    description: str | None = None
    enabled: bool = True
    catalog: str = DEFAULT_CATALOG


def validate_table_id(table_id: str) -> str:
    """Return ``table_id`` if it looks like a CBS identifier (e.g. ``83625NED``).

    Guards against path traversal / typos, because the id becomes a folder name.
    """
    if not isinstance(table_id, str) or not _TABLE_ID_PATTERN.match(table_id):
        raise ConfigError(f"Invalid CBS table id: {table_id!r} (expected alphanumeric, e.g. '83625NED')")
    return table_id


def resolve_tables_config_path(root: Path = REPO_ROOT) -> Path:
    """Return the real config if present, otherwise the example config."""
    config_dir = root / CONFIG_DIR_NAME
    primary = config_dir / TABLES_CONFIG_NAME
    if primary.exists():
        return primary
    example = config_dir / TABLES_EXAMPLE_CONFIG_NAME
    if example.exists():
        logger.warning("%s not found; falling back to %s", primary.relative_to(root), example.relative_to(root))
        return example
    raise ConfigError(f"No table config found: expected {primary} or {example}")


def _parse_entry(entry: Any, key_id: str | None = None) -> TableConfig:
    if isinstance(entry, str) and key_id is None:
        return TableConfig(id=validate_table_id(entry.strip()))
    if entry is None and key_id is not None:
        return TableConfig(id=validate_table_id(key_id))
    if not isinstance(entry, dict):
        raise ConfigError(f"Unsupported table entry: {entry!r}")

    table_id = key_id
    if table_id is None:
        table_id = next((entry[k] for k in _ID_KEYS if entry.get(k)), None)
    if table_id is None:
        raise ConfigError(f"Table entry has no id (one of {_ID_KEYS}): {entry!r}")

    return TableConfig(
        id=validate_table_id(str(table_id).strip()),
        name=entry.get("name"),
        description=entry.get("description"),
        enabled=bool(entry.get("enabled", True)),
        catalog=str(entry.get("catalog") or DEFAULT_CATALOG),
    )


def parse_tables_config(data: Any) -> list[TableConfig]:
    """Parse the loaded YAML document into a list of :class:`TableConfig`.

    Duplicate ids raise :class:`ConfigError`. Disabled tables are kept in the
    result (filter with ``t.enabled``) so callers can report what was skipped.
    """
    if isinstance(data, list):  # bare list at top level
        data = {"tables": data}
    if not isinstance(data, dict) or "tables" not in data:
        raise ConfigError("Config must be a mapping with a top-level 'tables' key")

    raw_tables = data["tables"] or []
    if isinstance(raw_tables, dict):
        tables = [_parse_entry(v, key_id=str(k)) for k, v in raw_tables.items()]
    elif isinstance(raw_tables, list):
        tables = [_parse_entry(item) for item in raw_tables]
    else:
        raise ConfigError("'tables' must be a list or a mapping")

    seen: set[str] = set()
    for t in tables:
        key = t.id.lower()
        if key in seen:
            raise ConfigError(f"Duplicate table id in config: {t.id}")
        seen.add(key)
    return tables


def load_tables_config(path: Path | None = None, root: Path = REPO_ROOT) -> list[TableConfig]:
    """Read and parse the table config (``config/cbs_tables.yaml`` or the example)."""
    config_path = path or resolve_tables_config_path(root)
    with config_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    tables = parse_tables_config(data)
    logger.info("Loaded %d table(s) from %s", len(tables), config_path.name)
    return tables
