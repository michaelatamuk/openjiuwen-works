# Windows parity for `make check`. Uses the project venv explicitly.
$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

Push-Location $root
try {
    & $python -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { throw "ruff check failed" }
    & $python -m ruff format --check src tests
    if ($LASTEXITCODE -ne 0) { throw "ruff format failed" }
    & $python -m mypy
    if ($LASTEXITCODE -ne 0) { throw "mypy failed" }
    & $python -m pytest tests -q -m "not slow" --cov=src/works --cov-report=term-missing
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
    Write-Host "check: green" -ForegroundColor Green
}
finally {
    Pop-Location
}
