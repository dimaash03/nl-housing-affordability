PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin

.PHONY: setup setup-locked lock ingest load transform check export build reproduce notebook test lint format clean-data help

# Extra pytest arguments, e.g. in a sandbox that blocks local sockets:  make test PYTEST_ARGS='-m "not loopback"'
PYTEST_ARGS ?=

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
	   $(BIN)/pip freeze --exclude-editable | grep -viE '^(pyproj|shapely|topojson)=='; } > requirements.lock
	@if $(BIN)/python -c "import shapely, pyproj, topojson" 2>/dev/null; then \
	  { echo "# Exact versions of the geo extras the boundary build was last tested with (QA G-5)."; \
	    echo "# Install on top of requirements.lock:  pip install -r requirements-geo.lock   (or: make setup-geo)"; \
	    echo "# Generated with \`make lock\` on Python $$($(BIN)/python -c 'import platform; print(platform.python_version() + ", " + platform.system())'), $$(date +%F)."; \
	    $(BIN)/pip freeze --exclude-editable | grep -iE '^(pyproj|shapely|topojson)=='; } > requirements-geo.lock; \
	fi

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

export:  ## Export the marts tables to data/processed/marts/*.parquet (for Power BI)
	$(BIN)/python -m nl_housing.export

build:  ## load -> transform -> check -> export (data/raw/ must already be downloaded)
	$(MAKE) load
	$(MAKE) transform
	$(MAKE) check
	$(MAKE) export

reproduce:  ## Full run from an empty data/ folder: ingest + build (needs internet for CBS)
	$(MAKE) ingest
	$(MAKE) build

notebook:  ## Run the analysis notebook top to bottom in place (asserts, figures, README key findings); stop open kernels first
	$(BIN)/jupyter nbconvert --to notebook --execute --inplace \
		--ExecutePreprocessor.timeout=600 --ExecutePreprocessor.record_timing=False \
		notebooks/01_affordability_findings.ipynb

test:  ## Run the offline unit tests (PYTEST_ARGS=... for extra pytest options)
	$(BIN)/python -m pytest $(PYTEST_ARGS)

lint:  ## Lint and check formatting with ruff (config in pyproject.toml)
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format:  ## Auto-fix lint findings and format the code with ruff
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

clean-data:  ## Delete downloaded data and the DuckDB file (keeps .gitkeep)
	find data/raw data/processed -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec rm -rf {} +
	rm -f data/nl_housing.duckdb data/nl_housing.duckdb.wal

.PHONY: setup-geo geo

setup-geo:  ## Install the optional geo extras (exact versions from requirements-geo.lock) into .venv
	$(BIN)/pip install -r requirements-geo.lock

geo:  ## Download + simplify the 2026 municipality boundaries into data/reference/ (FORCE=1 to re-download)
	$(BIN)/python -m nl_housing.geo $(if $(FORCE),--force,)
