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


# --- Project settings (single source of truth for the SQL models) --------------

_GM_CODE = re.compile(r"^GM\d{4}$")
_PV_CODE = re.compile(r"^PV\d{2}$")


@dataclass(frozen=True)
class ProjectSettings:
    """Analysis parameters from the ``project:`` section of ``config/cbs_tables.yaml``.

    ``nl_housing.transform`` writes these values to ``reference.project_settings`` before it builds
    the models, so the SQL reads the analysis window, the G4 list and the Randstad provinces from
    the config instead of repeating them as literals.
    """

    year_from: int
    year_to: int
    g4_codes: tuple[str, ...]
    randstad_province_codes: tuple[str, ...]
    low_reliability_max_households: int

    @property
    def base_year(self) -> int:
        """Base year of every growth column (= first year of the analysis window, D-008)."""
        return self.year_from

    @property
    def n_years(self) -> int:
        return self.year_to - self.year_from + 1


def _code_list(value: Any, pattern: re.Pattern[str], key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"project.{key} must be a non-empty list of codes")
    codes = tuple(str(v).strip() for v in value)
    bad = [c for c in codes if not pattern.match(c)]
    if bad:
        raise ConfigError(f"project.{key} has invalid codes {bad} (expected pattern {pattern.pattern})")
    if len(set(codes)) != len(codes):
        raise ConfigError(f"project.{key} lists a code more than once: {list(codes)}")
    return codes


def parse_project_settings(data: Any) -> ProjectSettings:
    """Parse and validate the ``project:`` section of the loaded YAML document."""
    project = data.get("project") if isinstance(data, dict) else None
    if not isinstance(project, dict):
        raise ConfigError("Config has no 'project' section (analysis_years, randstad_g4, randstad_provinces, ...)")

    years = project.get("analysis_years")
    if (
        not isinstance(years, list)
        or len(years) != 2
        or not all(isinstance(y, int) and not isinstance(y, bool) for y in years)
        or years[0] > years[1]
    ):
        raise ConfigError(f"project.analysis_years must be [first_year, last_year] (integers), got {years!r}")

    threshold = project.get("low_reliability_max_households")
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 0:
        raise ConfigError(f"project.low_reliability_max_households must be a non-negative integer, got {threshold!r}")

    return ProjectSettings(
        year_from=years[0],
        year_to=years[1],
        g4_codes=_code_list(project.get("randstad_g4"), _GM_CODE, "randstad_g4"),
        randstad_province_codes=_code_list(project.get("randstad_provinces"), _PV_CODE, "randstad_provinces"),
        low_reliability_max_households=threshold,
    )


def load_project_settings(path: Path | None = None, root: Path = REPO_ROOT) -> ProjectSettings:
    """Read the ``project:`` section of the table config (``config/cbs_tables.yaml`` or the example)."""
    config_path = path or resolve_tables_config_path(root)
    with config_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    settings = parse_project_settings(data)
    logger.info(
        "Project settings from %s: years %d-%d, %d G4 code(s), %d Randstad province(s)",
        config_path.name,
        settings.year_from,
        settings.year_to,
        len(settings.g4_codes),
        len(settings.randstad_province_codes),
    )
    return settings
