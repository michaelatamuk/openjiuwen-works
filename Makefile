.PHONY: check lint format type test unit integration cov bench wheel security gitleaks demo docs-links sbom api-compat

check: lint format type cov

lint:
	uv run ruff check src tests

format:
	uv run ruff format --check src tests

docs-links:
	uv run python scripts/check_docs_links.py

api-compat:
	uv run python scripts/check_api_compat.py docs/reference/openapi.baseline.json docs/reference/openapi.json

sbom:
	mkdir -p dist
	uv run --with cyclonedx-py cyclonedx-py environment --of json -o dist/sbom.json

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
	uv run python scripts/bench_api.py

wheel:
	uv build --wheel
	uv run python scripts/check_wheel.py dist/*.whl
	uv run python scripts/smoke_wheel.py --wheel dist/*.whl

security:
	uv run bandit -q -r src -c pyproject.toml
	uv run pip-audit

gitleaks:
	gitleaks detect --source . --no-banner

demo:
	powershell -ExecutionPolicy Bypass -File scripts/demo-m0.ps1
