# M0 demo: submit -> dry run -> a test edit refused -> the whole loop -> ledger.
# Run from the repository with: powershell -ExecutionPolicy Bypass -File scripts/demo-m0.ps1
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:WORKS_LOG_LEVEL = "WARNING"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\python.exe"
$demo = Join-Path $env:TEMP "works-demo"
$workspace = Join-Path $demo "works"
$repo = Join-Path $demo "repo"

Remove-Item $demo -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $workspace | Out-Null
Copy-Item (Join-Path $root "fixtures\fixture-repo") $repo -Recurse
Copy-Item (Join-Path $root "flows") (Join-Path $workspace "flows") -Recurse
& git -C $repo init -q -b main
& git -C $repo config core.autocrlf false
& git -C $repo config core.eol lf
& git -C $repo add -A
& git -C $repo -c user.name=demo -c user.email=demo@local commit -q -m "fixture with a planted bug"

function Works { & $python -m works --home $workspace @args }

Write-Host "`n== 1. submit ==" -ForegroundColor Cyan
$submitted = Works submit --ref "DEMO-1" --title "add returns a difference" --repo $repo --json | ConvertFrom-Json
$taskId = $submitted.task.id
Write-Host "task: $taskId (created: $($submitted.created))"

Write-Host "`n== 2. dry run ==" -ForegroundColor Cyan
Works run $taskId --dry-run --scenarios (Join-Path $root "fixtures\scenarios\fix-add.yaml") | Out-Null
$state = (Works status $taskId --json | ConvertFrom-Json).task.state
Write-Host "nodes and scenarios printed above; the task is still $state"

Write-Host "`n== 3. a test edit is refused before any command runs ==" -ForegroundColor Cyan
$policy = Works policy check tests/test_core.py --json | ConvertFrom-Json
$policyCode = $LASTEXITCODE
Write-Host "violation: $($policy.violations[0].path) / $($policy.violations[0].reason)"
Write-Host "policy exit code: $policyCode (expected 3)"

Write-Host "`n== 4. the whole loop with a recorded harness trace ==" -ForegroundColor Cyan
Works run $taskId --approve-plan --scenarios (Join-Path $root "fixtures\scenarios\fix-add.yaml") --trace (Join-Path $root "fixtures\traces\fix-add.json")
$runCode = $LASTEXITCODE
Write-Host "run exit code: $runCode (expected 0)"

Write-Host "`n== 5. status and ledger ==" -ForegroundColor Cyan
Works status
Works ledger
$proof = Get-ChildItem (Join-Path $workspace "runs") -Recurse -Filter evidence.md | Select-Object -First 1
Write-Host "`nproof: $($proof.FullName)"
Get-Content $proof.FullName -TotalCount 24

if ($policyCode -ne 3 -or $runCode -ne 0 -or $state -ne "queued") {
    Write-Host "`ndemo: FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "`ndemo: green - the fix is proved and the ledger has a row" -ForegroundColor Green
exit 0
