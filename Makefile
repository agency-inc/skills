SCRIPTS_DIR := plugins/agency-knows/skills/kb-github/scripts

.PHONY: lint format typecheck install test

lint:
	uvx ruff check $(SCRIPTS_DIR)/src

format:
	uvx ruff format $(SCRIPTS_DIR)/src
	uvx ruff check --fix $(SCRIPTS_DIR)/src

typecheck:
	cd $(SCRIPTS_DIR) && uvx pyright src

install:
	cd $(SCRIPTS_DIR) && uv venv .venv && uv pip install -e "."

check: lint typecheck
