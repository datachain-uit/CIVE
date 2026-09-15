$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$checkpoint = Join-Path $repo 'results\llm_daily_full_llama3_repeat2.json'
$pythonExe = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$inferencePid = 14800

if (-not (Test-Path -LiteralPath $repo -PathType Container)) {
    throw "Missing repository: $repo"
}
if (-not (Test-Path -LiteralPath $checkpoint -PathType Leaf)) {
    throw "Missing checkpoint: $checkpoint"
}
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw "Missing Python runtime: $pythonExe"
}

Set-Location -LiteralPath $repo

try {
    while (Get-Process -Id $inferencePid -ErrorAction SilentlyContinue) {
        $state = Get-Content -LiteralPath $checkpoint -Raw | ConvertFrom-Json
        $count = @($state.records).Count
        $lastDate = if ($count -gt 0) { $state.records[-1].information_date } else { 'none' }
        Write-Output "WAIT completed=$count last_date=$lastDate errors=$($state.summary.errors) time=$(Get-Date -Format o)"
        Start-Sleep -Seconds 50
    }
}
finally {
    powercfg /setactive SCHEME_BALANCED
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to restore the Balanced power plan'
    }
    Write-Output 'POWER_PLAN_RESTORED=Balanced'
}

$final = Get-Content -LiteralPath $checkpoint -Raw | ConvertFrom-Json
$recordCount = @($final.records).Count
$successCount = [int]$final.summary.success
$errorCount = [int]$final.summary.errors
if ($recordCount -ne 2927 -or $successCount -ne 2927 -or $errorCount -ne 0) {
    throw "Inference incomplete: records=$recordCount success=$successCount errors=$errorCount"
}
$uniqueHashes = @($final.records | ForEach-Object { $_.content_hash } | Sort-Object -Unique).Count
if ($uniqueHashes -ne 2927) {
    throw "Inference hash-set invalid: unique=$uniqueHashes expected=2927"
}
Write-Output 'INFERENCE_VALIDATED records=2927 success=2927 errors=0 unique_hashes=2927'

$env:PYTHONPATH = Join-Path $repo '.venv\Lib\site-packages'

& $pythonExe executor\audit_llm_determinism.py `
    --left results\llm_daily_full_llama3_development.json `
    --right results\llm_daily_full_llama3_repeat2.json `
    --output results\llm_daily_full_llama3_repeat2_determinism.json
if ($LASTEXITCODE -ne 0) { throw 'Determinism audit failed' }

& $pythonExe executor\build_llm_dual_run_consensus.py `
    --left results\llm_daily_full_llama3_development.json `
    --right results\llm_daily_full_llama3_repeat2.json `
    --output results\llm_daily_dual_run_consensus_v1.json
if ($LASTEXITCODE -ne 0) { throw 'Consensus build failed' }

& $pythonExe executor\llm_lifecycle_adapter.py `
    --scores results\llm_daily_dual_run_consensus_v1.json `
    --lifecycle-manifest results\bybit_lifecycle_universe.json `
    --output results\llm_daily_dual_run_consensus_v1_targets.json
if ($LASTEXITCODE -ne 0) { throw 'Lifecycle adapter failed' }

& $pythonExe executor\llm_bybit_lifecycle_execution.py `
    --scores results\llm_daily_dual_run_consensus_v1.json `
    --lifecycle-manifest results\bybit_lifecycle_universe.json `
    --output results\llm_bybit_lifecycle_dual_run_consensus_v1_development.json `
    --daily-cache-dir results\bybit_lifecycle_daily `
    --four-h-cache-dir results\bybit_lifecycle_4h `
    --funding-cache-dir results\bybit_lifecycle_funding `
    --stop-atr 3 `
    --trail-atr 4 `
    --gross-leverage 1 `
    --workers 6
if ($LASTEXITCODE -ne 0) { throw 'Consensus lifecycle backtest failed' }

& $pythonExe executor\audit_llm_outcome_calibration.py `
    --scores results\llm_daily_dual_run_consensus_v1.json `
    --btc-bars results\bybit_lifecycle_4h\BTCUSDT_1660348800000_1786492800000.json `
    --output results\llm_outcome_calibration_dual_run_consensus_v1_development.json
if ($LASTEXITCODE -ne 0) { throw 'Consensus calibration failed' }

& $pythonExe -m unittest discover -s executor -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed' }

& $pythonExe executor\freeze_experiment.py --verify
if ($LASTEXITCODE -ne 0) { throw 'Tech freeze verification failed' }

Write-Output 'POSTPROCESS_COMPLETE'
