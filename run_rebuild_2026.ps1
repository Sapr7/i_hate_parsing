$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$log = Join-Path $PSScriptRoot "output\rebuild_2026_log.txt"

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Output $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

"" | Set-Content $log -Encoding UTF8
Log "=== REBUILD 2020-2026 ==="

Log "Phase 1: EIS + Rosatom discovery..."
& $py -u (Join-Path $PSScriptRoot "run_full_pipeline.py") --discovery-only 2>&1 | Tee-Object -FilePath (Join-Path $PSScriptRoot "output\discovery_2026_log.txt") -Append
if ($LASTEXITCODE -ne 0) { Log "Phase 1 FAILED exit=$LASTEXITCODE"; exit $LASTEXITCODE }

Log "Phase 2: Rosatom keyword scan..."
& $py -u -m procurement.rosatom_keyword_scan 2>&1 | Tee-Object -FilePath (Join-Path $PSScriptRoot "output\rosatom_keyword_log.txt") -Append
if ($LASTEXITCODE -ne 0) { Log "Phase 2 FAILED exit=$LASTEXITCODE"; exit $LASTEXITCODE }

Log "Phase 3: Merge + Bothub filter..."
& $py -u (Join-Path $PSScriptRoot "run_full_pipeline.py") --skip-discovery --skip-rosatom-detail 2>&1 | Tee-Object -FilePath (Join-Path $PSScriptRoot "output\pipeline_bothub_log.txt") -Append
if ($LASTEXITCODE -ne 0) { Log "Phase 3 FAILED exit=$LASTEXITCODE"; exit $LASTEXITCODE }

Log "=== REBUILD DONE ==="