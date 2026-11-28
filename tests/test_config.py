from pathlib import Path

import pytest

from nl_housing import config
from nl_housing.config import ConfigError, TableConfig


def test_parse_list_of_mappings():
    tables = config.parse_tables_config(
        {"tables": [{"id": "83625NED", "name": "prices", "enabled": False}, {"table_id": "85773NED"}]}
    )
    assert tables == [
        TableConfig(id="83625NED", name="prices", enabled=False),
        TableConfig(id="85773NED"),
    ]


def test_parse_list_of_strings_and_mapping_form():
    assert [t.id for t in config.parse_tables_config({"tables": ["83625NED"]})] == ["83625NED"]
    tables = config.parse_tables_config({"tables": {"83625NED": {"name": "prices"}, "85773NED": None}})
    assert [(t.id, t.name) for t in tables] == [("83625NED", "prices"), ("85773NED", None)]


def test_parse_top_level_list():
    assert [t.id for t in config.parse_tables_config(["83625NED"])] == ["83625NED"]


def test_defaults():
    t = config.parse_tables_config({"tables": [{"id": "83625NED"}]})[0]
    assert t.enabled is True and t.catalog == "opendata.cbs.nl"


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"no_tables": []},
        {"tables": "83625NED"},
        {"tables": [{"name": "missing id"}]},
        {"tables": [{"id": "../etc"}]},
        {"tables": ["83625NED", "83625ned"]},  # duplicate (case-insensitive)
    ],
)
def test_invalid_configs_raise(data):
    with pytest.raises(ConfigError):
        config.parse_tables_config(data)


def test_empty_tables_list_is_allowed():
    assert config.parse_tables_config({"tables": None}) == []


def test_resolve_prefers_real_config(repo_root: Path, write_config):
    write_config("tables: []", name="cbs_tables.example.yaml")
    real = write_config("tables: []")
    assert config.resolve_tables_config_path(repo_root) == real


def test_resolve_falls_back_to_example(repo_root: Path, write_config):
    example = write_config("tables: []", name="cbs_tables.example.yaml")
    assert config.resolve_tables_config_path(repo_root) == example


def test_resolve_missing_raises(repo_root: Path):
    with pytest.raises(ConfigError):
        config.resolve_tables_config_path(repo_root)


def test_load_tables_config_from_file(repo_root: Path, write_config):
    write_config("tables:\n  - id: 83625NED\n    description: prices\n")
    tables = config.load_tables_config(root=repo_root)
    assert tables == [TableConfig(id="83625NED", description="prices")]


def test_repo_example_config_is_valid():
    """The committed example file must always parse."""
    example = config.REPO_ROOT / "config" / config.TABLES_EXAMPLE_CONFIG_NAME
    tables = config.load_tables_config(path=example)
    assert len(tables) == 1


def test_paths_are_relative_to_root(tmp_path: Path):
    assert config.raw_dir(tmp_path) == tmp_path / "data" / "raw"
    assert config.processed_dir(tmp_path) == tmp_path / "data" / "processed"
    assert config.duckdb_path(tmp_path) == tmp_path / "data" / "nl_housing.duckdb"
    assert config.raw_table_dir("83625NED", tmp_path) == tmp_path / "data" / "raw" / "83625NED"


def test_raw_table_dir_rejects_unsafe_ids(tmp_path: Path):
    for bad in ["../x", "a/b", "", "83625 NED"]:
        with pytest.raises(ConfigError):
            config.raw_table_dir(bad, tmp_path)


def test_repo_root_points_at_repository():
    assert (config.REPO_ROOT / "src" / "nl_housing" / "config.py").exists()


# --- Project settings ----------------------------------------------------------

VALID_PROJECT = {
    "analysis_years": [2011, 2025],
    "randstad_g4": ["GM0363", "GM0599", "GM0518", "GM0344"],
    "randstad_provinces": ["PV26", "PV27", "PV28"],
    "low_reliability_max_households": 5000,
}


def test_parse_project_settings():
    s = config.parse_project_settings({"project": VALID_PROJECT})
    assert (s.year_from, s.year_to, s.base_year, s.n_years) == (2011, 2025, 2011, 15)
    assert s.g4_codes == ("GM0363", "GM0599", "GM0518", "GM0344")
    assert s.randstad_province_codes == ("PV26", "PV27", "PV28")


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("analysis_years", [2025, 2011], "analysis_years"),
        ("analysis_years", [2011], "analysis_years"),
        ("analysis_years", ["2011", 2025], "analysis_years"),
        ("randstad_g4", ["GM363"], "invalid codes"),
        ("randstad_g4", ["GM0363", "GM0363"], "more than once"),
        ("randstad_provinces", [], "non-empty"),
        ("low_reliability_max_households", -1, "non-negative"),
    ],
)
def test_parse_project_settings_rejects_bad_values(key: str, value: object, message: str):
    with pytest.raises(ConfigError, match=message):
        config.parse_project_settings({"project": {**VALID_PROJECT, key: value}})


def test_parse_project_settings_requires_section():
    with pytest.raises(ConfigError, match="project"):
        config.parse_project_settings({"tables": []})


@pytest.mark.parametrize("name", [config.TABLES_CONFIG_NAME, config.TABLES_EXAMPLE_CONFIG_NAME])
def test_repo_configs_hold_the_agreed_settings(name: str):
    """Both committed configs carry the D-008 / D-009 / D-010 values (the SQL reads them from here)."""
    s = config.load_project_settings(path=config.REPO_ROOT / "config" / name)
    assert config.parse_project_settings({"project": VALID_PROJECT}) == s
