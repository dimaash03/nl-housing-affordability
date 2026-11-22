PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin

.PHONY: setup setup-locked lock ingest load transform check test lint format clean-data help

help:  ## Show available targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup:  ## Create .venv and install dependencies + the nl_housing package (editable)
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/pip install -e .

setup-locked:  ## Like setup, but with the exact versions from requirements.lock (Python >= 3.12)
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.lock
	$(BIN)/pip install -e .

lock:  ## Regenerate requirements.lock from the current .venv (commit it with the change that needed it)
	@{ echo "# Exact versions of the environment the pipeline was last run and tested with (review finding C4)."; \
	   echo "# Generated with \`make lock\` (pip freeze --exclude-editable) on Python $$($(BIN)/python -c 'import platform; print(platform.python_version() + ", " + platform.system())'), $$(date +%F)."; \
	   echo "# Install: pip install -r requirements.lock && pip install -e ."; \
	   $(BIN)/pip freeze --exclude-editable; } > requirements.lock

ingest:  ## Download all CBS tables from config/cbs_tables.yaml into data/raw/ (FORCE=1 to re-download)
	$(BIN)/python -m nl_housing.ingest $(if $(FORCE),--force,)

load:  ## Load data/raw/ (schema raw) and the committed herindeling mapping (schema reference) into DuckDB
	$(BIN)/python -m nl_housing.load_duckdb
	$(BIN)/python -m nl_housing.harmonise --load-only

.PHONY: harmonise
harmonise:  ## Rebuild data/reference/municipality_mapping_2026.csv from data/raw/ and load it (commit the CSV diff)
	$(BIN)/python -m nl_housing.harmonise --load-duckdb

transform:  ## Build the SQL models (sql/models.yaml order) into schemas staging / marts
	$(BIN)/python -m nl_housing.transform

check:  ## Run the SQL data tests (sql/tests/*.sql) against the built database
	$(BIN)/python -m nl_housing.check

test:  ## Run the offline unit tests
	$(BIN)/python -m pytest

lint:  ## Lint and check formatting with ruff (config in pyproject.toml)
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format:  ## Auto-fix lint findings and format the code with ruff
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

clean-data:  ## Delete downloaded data and the DuckDB file (keeps .gitkeep)
	find data/raw data/processed -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec rm -rf {} +
	rm -f data/nl_housing.duckdb data/nl_housing.duckdb.wal
