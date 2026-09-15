$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDirectory = Join-Path $workspaceRoot 'runtime\logs\llm'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonExe = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$model = 'ProsusAI/finbert'
$revision = '4556d13015211d73dccd3fdd39d39232506f3e43'
$cacheDirectory = if ($env:KLTN_HF_CACHE) { $env:KLTN_HF_CACHE } else { Join-Path $repo 'models\huggingface' }
$config = 'configs\llm_finbert_financial_sentiment_v1_development.json'
$stage1Gate = 'results\llm_finbert_operational_gate_v1.json'
$full = 'results\llm_daily_full_finbert_v1_development.json'
$calibration = 'results\llm_finbert_predictive_gate_v1_development.json'
$bars = 'results\bybit_lifecycle_4h\BTCUSDT_1660348800000_1786492800000.json'
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 5
$expectedRecords = 2927
$sessionId = Get-Date -Format 'yyyyMMdd_HHmmss'
$scorer = $null

foreach ($path in @($repo, $pythonExe, $cacheDirectory, (Join-Path $repo $config), (Join-Path $repo $stage1Gate), (Join-Path $repo $bars))) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}
$gatePayload = Get-Content -Raw -LiteralPath (Join-Path $repo $stage1Gate) | ConvertFrom-Json
if (-not $gatePayload.passed -or $gatePayload.status -ne 'stage1-pass-full-calibration-authorized') {
    throw 'FinBERT Stage 2 is not authorized by Stage 1 gate'
}

function Set-BalancedPowerPlan {
    powercfg /setactive SCHEME_BALANCED | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to activate Windows Balanced' }
}

function Get-GpuTemperatureC {
    $raw = & nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits
    if ($LASTEXITCODE -ne 0 -or @($raw).Count -ne 1) { throw 'Cannot read exactly one NVIDIA GPU temperature; failing closed' }
    $temperature = 0
    if (-not [int]::TryParse(([string]$raw).Trim(), [ref]$temperature)) { throw "Cannot parse GPU temperature: $raw" }
    return $temperature
}

function Get-RunState {
    $path = Join-Path $repo $full
    if (-not (Test-Path -LiteralPath $path)) { return [pscustomobject]@{ Records=0; Success=0; Errors=0; Unique=0 } }
    $payload = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    return [pscustomobject]@{
        Records=@($payload.records).Count
        Success=[int]$payload.summary.success
        Errors=[int]$payload.summary.errors
        Unique=@($payload.records.content_hash | Sort-Object -Unique).Count
    }
}

function Stop-Scorer {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process) { return }
    $Process.Refresh()
    if ($Process.HasExited) { return }
    $live = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
    if ($live -and $live.ProcessName -ne 'python') { throw "Scorer PID $($Process.Id) changed identity" }
    if ($live) { Stop-Process -Id $Process.Id -Force -ErrorAction Stop; $Process.WaitForExit(10000) | Out-Null }
}

function Invoke-PythonStep {
    param([string]$Label, [string[]]$Arguments)
    $temperature = Get-GpuTemperatureC
    if ($temperature -ge $hardCeilingC) { throw "$Label refused at GPU temperature ${temperature}C" }
    & $pythonExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
}

Set-Location -LiteralPath $repo
Set-BalancedPowerPlan
$env:PYTHONPATH = "$(Join-Path $repo 'executor');$(Join-Path $repo '.venv\Lib\site-packages')"

try {
    $state = Get-RunState
    if ($state.Errors -gt 0 -or $state.Records -gt $expectedRecords -or $state.Unique -ne $state.Records) {
        throw "Invalid FinBERT full checkpoint: records=$($state.Records) errors=$($state.Errors) unique=$($state.Unique)"
    }
    if ($state.Records -lt $expectedRecords) {
        $temperature = Get-GpuTemperatureC
        while ($temperature -gt $resumeAtC) {
            Write-Output "COOLDOWN gpu_temp_c=$temperature records=$($state.Records)"
            Start-Sleep -Seconds $pollSeconds
            $temperature = Get-GpuTemperatureC
        }
        $stdout = Join-Path $logDirectory "finbert_stage2_${sessionId}.stdout.log"
        $stderr = Join-Path $logDirectory "finbert_stage2_${sessionId}.stderr.log"
        $arguments = @(
            'executor\score_finbert_daily_information_sets.py',
            '--input', 'results\llm_daily_information_sets_v1.json', '--output', $full,
            '--model', $model, '--revision', $revision, '--cache-dir', $cacheDirectory,
            '--run-id', 'finbert-stage2-full-v1-development', '--batch-size', '16',
            '--max-length', '128', '--threads', '2'
        )
        $script:scorer = Start-Process -FilePath $pythonExe -ArgumentList $arguments `
            -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        try { $script:scorer.PriorityClass = 'BelowNormal' } catch { }
        Write-Output "SCORING_START pid=$($script:scorer.Id) records=$($state.Records) gpu_temp_c=$temperature"
        while (-not $script:scorer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $script:scorer.Refresh()
            $temperature = Get-GpuTemperatureC
            $state = Get-RunState
            Write-Output "THERMAL gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
            if ($state.Errors -gt 0) {
                Stop-Scorer $script:scorer; $script:scorer=$null; Set-BalancedPowerPlan
                throw "SCHEMA_STOP records=$($state.Records) errors=$($state.Errors)"
            }
            if ($temperature -ge $hardCeilingC) {
                Stop-Scorer $script:scorer; $script:scorer=$null; Set-BalancedPowerPlan
                throw "THERMAL_STOP gpu_temp_c=$temperature records=$($state.Records)"
            }
        }
        $script:scorer.WaitForExit(); $script:scorer.Refresh(); $exitCode=$script:scorer.ExitCode; $script:scorer=$null
        if ($exitCode -ne 0) { throw "FinBERT full inference failed: exit=$exitCode stderr=$stderr" }
    }
    $state = Get-RunState
    if ($state.Records -ne $expectedRecords -or $state.Success -ne $expectedRecords -or $state.Unique -ne $expectedRecords) {
        throw "FinBERT full inference incomplete: records=$($state.Records) success=$($state.Success) unique=$($state.Unique)"
    }
    Invoke-PythonStep 'predictive-gate' @(
        'executor\evaluate_finbert_predictive_gate.py', '--config', $config,
        '--scores', $full, '--btc-bars', $bars, '--output', $calibration
    )
    Invoke-PythonStep 'regression-tests' @('-m','unittest','discover','-s','executor','-p','test_*.py')
    Write-Output 'FINBERT_STAGE2_COMPLETE'
}
finally {
    if ($null -ne $scorer) { Stop-Scorer $scorer }
    Remove-EmptyRedirectLogs -Directory $logDirectory
    Set-BalancedPowerPlan
    Write-Output 'SAFETY_CLEANUP_COMPLETE power_plan=Balanced'
}
