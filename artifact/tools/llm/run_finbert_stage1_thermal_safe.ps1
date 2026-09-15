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
$runs = @(
    'results\llm_daily_reliability_finbert_run1_v1.json',
    'results\llm_daily_reliability_finbert_run2_v1.json'
)
$audit = 'results\llm_daily_reliability_finbert_determinism_v1.json'
$gate = 'results\llm_finbert_operational_gate_v1.json'
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 5
$expectedRecords = 108
$sessionId = Get-Date -Format 'yyyyMMdd_HHmmss'
$scorer = $null

foreach ($path in @($repo, $pythonExe, (Join-Path $repo $config), $cacheDirectory)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}

function Set-BalancedPowerPlan {
    powercfg /setactive SCHEME_BALANCED | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to activate Windows Balanced' }
}

function Get-GpuTemperatureC {
    $raw = & nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits
    if ($LASTEXITCODE -ne 0 -or @($raw).Count -ne 1) {
        throw 'Cannot read exactly one NVIDIA GPU temperature; failing closed'
    }
    $temperature = 0
    if (-not [int]::TryParse(([string]$raw).Trim(), [ref]$temperature)) {
        throw "Cannot parse NVIDIA GPU temperature: $raw"
    }
    return $temperature
}

function Get-RunState {
    param([string]$RelativePath)
    $path = Join-Path $repo $RelativePath
    if (-not (Test-Path -LiteralPath $path)) {
        return [pscustomobject]@{ Records = 0; Success = 0; Errors = 0; Unique = 0 }
    }
    $payload = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    return [pscustomobject]@{
        Records = @($payload.records).Count
        Success = [int]$payload.summary.success
        Errors = [int]$payload.summary.errors
        Unique = @($payload.records.content_hash | Sort-Object -Unique).Count
    }
}

function Stop-Scorer {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process) { return }
    $Process.Refresh()
    if ($Process.HasExited) { return }
    $live = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
    if ($live -and $live.ProcessName -ne 'python') {
        throw "Scorer PID $($Process.Id) changed identity to $($live.ProcessName)"
    }
    if ($live) {
        Stop-Process -Id $Process.Id -Force -ErrorAction Stop
        $Process.WaitForExit(10000) | Out-Null
    }
}

function Invoke-ScoringRun {
    param([int]$RunNumber, [string]$RelativeOutput)
    $state = Get-RunState $RelativeOutput
    if ($state.Errors -gt 0) {
        throw "Run $RunNumber already contains schema errors; Stage 1 cannot pass"
    }
    if ($state.Records -eq $expectedRecords -and $state.Unique -eq $expectedRecords) { return }
    if ($state.Records -gt $expectedRecords -or $state.Unique -ne $state.Records) {
        throw "Invalid checkpoint for run ${RunNumber}: records=$($state.Records) unique=$($state.Unique)"
    }

    $temperature = Get-GpuTemperatureC
    while ($temperature -gt $resumeAtC) {
        Write-Output "COOLDOWN run=$RunNumber gpu_temp_c=$temperature time=$(Get-Date -Format o)"
        Start-Sleep -Seconds $pollSeconds
        $temperature = Get-GpuTemperatureC
    }

    $stdout = Join-Path $logDirectory "finbert_${sessionId}_run_${RunNumber}.stdout.log"
    $stderr = Join-Path $logDirectory "finbert_${sessionId}_run_${RunNumber}.stderr.log"
    $arguments = @(
        'executor\score_finbert_daily_information_sets.py',
        '--input', 'results\llm_daily_information_sets_v1.json',
        '--output', $RelativeOutput,
        '--model', $model,
        '--revision', $revision,
        '--cache-dir', $cacheDirectory,
        '--run-id', "finbert-stage1-run$RunNumber-v1",
        '--sample-per-year', '12',
        '--batch-size', '16',
        '--max-length', '128',
        '--threads', '2'
    )
    $script:scorer = Start-Process -FilePath $pythonExe -ArgumentList $arguments `
        -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr -PassThru
    try { $script:scorer.PriorityClass = 'BelowNormal' } catch { }
    Write-Output "SCORING_START run=$RunNumber pid=$($script:scorer.Id) records=$($state.Records) gpu_temp_c=$temperature"

    while (-not $script:scorer.HasExited) {
        Start-Sleep -Seconds $pollSeconds
        $script:scorer.Refresh()
        $temperature = Get-GpuTemperatureC
        $state = Get-RunState $RelativeOutput
        Write-Output "THERMAL run=$RunNumber gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
        if ($state.Errors -gt 0) {
            Stop-Scorer $script:scorer
            $script:scorer = $null
            Set-BalancedPowerPlan
            throw "IRREVERSIBLE_SCHEMA_STOP run=$RunNumber records=$($state.Records) errors=$($state.Errors)"
        }
        if ($temperature -ge $hardCeilingC) {
            Stop-Scorer $script:scorer
            $script:scorer = $null
            Set-BalancedPowerPlan
            throw "THERMAL_STOP run=$RunNumber gpu_temp_c=$temperature records=$($state.Records)"
        }
    }
    $script:scorer.WaitForExit()
    $script:scorer.Refresh()
    $exitCode = $script:scorer.ExitCode
    $script:scorer = $null
    $state = Get-RunState $RelativeOutput
    if ($exitCode -ne 0) { throw "Run $RunNumber failed: exit=$exitCode stderr=$stderr" }
    if ($state.Records -ne $expectedRecords -or $state.Success -ne $expectedRecords -or $state.Unique -ne $expectedRecords) {
        throw "Run $RunNumber incomplete: records=$($state.Records) success=$($state.Success) unique=$($state.Unique)"
    }
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
    for ($index = 0; $index -lt $runs.Count; $index += 1) {
        Invoke-ScoringRun ($index + 1) $runs[$index]
    }
    Invoke-PythonStep 'determinism-audit' @(
        'executor\audit_llm_determinism.py', '--left', $runs[0], '--right', $runs[1],
        '--long-threshold', '0', '--minimum-confidence', '0', '--output', $audit
    )
    Invoke-PythonStep 'operational-gate' @(
        'executor\evaluate_finbert_operational_gate.py', '--config', $config,
        '--audit', $audit, '--left', $runs[0], '--right', $runs[1], '--output', $gate
    )
    Invoke-PythonStep 'regression-tests' @(
        '-m', 'unittest', 'discover', '-s', 'executor', '-p', 'test_*.py'
    )
    Write-Output 'FINBERT_STAGE1_COMPLETE'
}
finally {
    if ($null -ne $scorer) { Stop-Scorer $scorer }
    Remove-EmptyRedirectLogs -Directory $logDirectory
    Set-BalancedPowerPlan
    Write-Output 'SAFETY_CLEANUP_COMPLETE power_plan=Balanced'
}
