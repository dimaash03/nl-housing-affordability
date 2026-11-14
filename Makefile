PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin

.PHONY: setup ingest load test clean-data help

help:  ## Show available targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup:  ## Create .venv and install dependencies + the nl_housing package (editable)
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/pip install -e .

ingest:  ## Download all CBS tables from config/cbs_tables.yaml into data/raw/ (FORCE=1 to re-download)
	$(BIN)/python -m nl_housing.ingest $(if $(FORCE),--force,)

load:  ## Load data/raw/ into data/nl_housing.duckdb (schema raw)
	$(BIN)/python -m nl_housing.load_duckdb

test:  ## Run the offline unit tests
	$(BIN)/python -m pytest

clean-data:  ## Delete downloaded data and the DuckDB file (keeps .gitkeep)
	find data/raw data/processed -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec rm -rf {} +
	rm -f data/nl_housing.duckdb data/nl_housing.duckdb.wal
