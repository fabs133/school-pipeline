.PHONY: install test test-live lint format check clean doctor hooks help

help:
	@echo "schulpipeline development targets:"
	@echo "  make install     Install package with dev dependencies"
	@echo "  make test        Run offline test suite"
	@echo "  make test-live   Run live API tests (requires keys)"
	@echo "  make lint        Run ruff linter"
	@echo "  make format      Run ruff formatter"
	@echo "  make check       Lint + test (CI equivalent)"
	@echo "  make clean       Remove build artifacts and caches"
	@echo "  make doctor      Run schulpipeline doctor command"
	@echo "  make hooks       Install pre-commit hooks"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --ignore=tests/live -x

test-live:
	pytest tests/live/ -v -x -m live

lint:
	ruff check schulpipeline/ tests/

format:
	ruff format schulpipeline/ tests/

check: lint test

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

doctor:
	python -m schulpipeline.cli doctor

hooks:
	pre-commit install
	@echo "Pre-commit hooks installed."
