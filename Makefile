PY ?= python

.PHONY: check lint format type test unit integration cov bench security gitleaks demo

check: lint type cov

lint:
	ruff check src tests

format:
	ruff format --check src tests

type:
	mypy

test:
	$(PY) -m pytest tests -q -m "not slow"

unit:
	$(PY) -m pytest tests -q -m "not slow" --ignore=tests/integration

integration:
	$(PY) -m pytest tests/integration -q

cov:
	$(PY) -m pytest tests -q -m "not slow" --cov=src/works --cov-report=term-missing

bench:
	$(PY) -m pytest tests/test_performance.py -q -m slow

security:
	bandit -q -r src -c pyproject.toml
	pip-audit

gitleaks:
	gitleaks detect --source . --no-banner

demo:
	powershell -ExecutionPolicy Bypass -File scripts/demo-m0.ps1
