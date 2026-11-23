.PHONY: check lint format type test unit integration cov bench security gitleaks demo

check: lint format type cov

lint:
	uv run ruff check src tests

format:
	uv run ruff format --check src tests

type:
	uv run mypy

test:
	uv run pytest tests -q -m "not slow"

unit:
	uv run pytest tests -q -m "not slow" --ignore=tests/integration

integration:
	uv run pytest tests/integration -q

cov:
	uv run pytest tests -q -m "not slow" --cov=src/works --cov-report=term-missing

bench:
	uv run pytest tests/integration/test_performance.py -q -m slow

security:
	uv run bandit -q -r src -c pyproject.toml
	uv run pip-audit

gitleaks:
	gitleaks detect --source . --no-banner

demo:
	powershell -ExecutionPolicy Bypass -File scripts/demo-m0.ps1
