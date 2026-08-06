.PHONY: help setup sync lint fmt typecheck test check

help:
	@echo "setup      - create venv and install (pip path)"
	@echo "sync       - install with uv (uv sync)"
	@echo "lint       - ruff lint"
	@echo "fmt        - ruff format"
	@echo "typecheck  - mypy"
	@echo "test       - pytest"
	@echo "check      - lint + typecheck + test"

setup:
	python -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt && pip install -e .

sync:
	uv sync --extra dev

lint:
	ruff check src tests

fmt:
	ruff format src tests

typecheck:
	mypy

test:
	pytest

check: lint typecheck test
