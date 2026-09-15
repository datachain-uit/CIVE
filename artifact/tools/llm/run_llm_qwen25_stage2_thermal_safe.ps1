$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDirectory = Join-Path $workspaceRoot 'runtime\logs\llm'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonExe = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$ollamaExe = if ($env:KLTN_OLLAMA_EXE) { $env:KLTN_OLLAMA_EXE } else { (Get-Command ollama -ErrorAction Stop).Source }
$ollamaServerRoot = if ($env:KLTN_OLLAMA_SERVER_ROOT) { $env:KLTN_OLLAMA_SERVER_ROOT } else { Split-Path -Parent $ollamaExe }
$model = 'qwen2.5:7b'
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 1
$expectedRecords = 2927
$requestDelaySeconds = 10
$sessionId = Get-Date -Format 'yyyyMMdd_HHmmss'
$scorer = $null

$config = 'configs\llm_qwen25_7b_challenger_v1_development.json'
$stage1 = 'results\llm_qwen25_7b_challenger_gate_v1.json'
$seed = 'results\llm_daily_reliability_qwen2_5_7b_run1_v1.json'
$full = 'results\llm_daily_full_qwen2_5_7b_v1_development.json'
$calibration = 'results\llm_outcome_calibration_qwen2_5_7b_v1_development.json'
$stage2 = 'results\llm_qwen25_7b_challenger_stage2_v1.json'

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

function Get-FullState {
    $path = Join-Path $repo $full
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

function Unload-LocalModel {
    try { & $ollamaExe stop $model | Out-Null }
    catch { Write-Output "OLLAMA_STOP_WARNING=$($_.Exception.Message)" }
    Start-Sleep -Seconds 2
    foreach ($server in @(Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue)) {
        if (-not $server.Path.StartsWith($ollamaServerRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to stop unexpected llama-server path: $($server.Path)"
        }
        Stop-Process -Id $server.Id -Force -ErrorAction Stop
    }
}

function Invoke-PythonStep {
    param([string]$Label, [string[]]$Arguments)
    $temperature = Get-GpuTemperatureC
    if ($temperature -ge $hardCeilingC) { throw "$Label refused at ${temperature}C" }
    Write-Output "STEP_START label=$Label gpu_temp_c=$temperature"
    & $pythonExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
    Write-Output "STEP_COMPLETE label=$Label"
}

foreach ($relative in @($config, $stage1, $seed)) {
    if (-not (Test-Path -LiteralPath (Join-Path $repo $relative))) {
        throw "Required artifact missing: $relative"
    }
}
$stage1Payload = Get-Content -LiteralPath (Join-Path $repo $stage1) -Raw | ConvertFrom-Json
if (-not $stage1Payload.passed) { throw 'Stage 1 did not authorize Stage 2' }

Set-Location -LiteralPath $repo
Set-BalancedPowerPlan
$env:PYTHONPATH = "$(Join-Path $repo 'executor');$(Join-Path $repo '.venv\Lib\site-packages')"

try {
    $cycle = 0
    while ($true) {
        $state = Get-FullState
        if ($state.Records -eq $expectedRecords) {
            if ($state.Success -ne $expectedRecords -or $state.Errors -ne 0 -or $state.Unique -ne $expectedRecords) {
                throw "Completed full checkpoint invalid: success=$($state.Success) errors=$($state.Errors) unique=$($state.Unique)"
            }
            break
        }
        if ($state.Records -gt $expectedRecords -or $state.Unique -ne $state.Records) {
            throw "Full checkpoint invalid: records=$($state.Records) unique=$($state.Unique)"
        }

        $temperature = Get-GpuTemperatureC
        while ($temperature -gt $resumeAtC) {
            Write-Output "COOLDOWN gpu_temp_c=$temperature records=$($state.Records)"
            Start-Sleep -Seconds $pollSeconds
            $temperature = Get-GpuTemperatureC
        }

        Remove-EmptyRedirectLogs -Directory $logDirectory
        $cycle += 1
        $stdout = Join-Path $logDirectory "qwen25_stage2_${sessionId}_cycle_${cycle}.stdout.log"
        $stderr = Join-Path $logDirectory "qwen25_stage2_${sessionId}_cycle_${cycle}.stderr.log"
        $arguments = @(
            'executor\score_llm_daily_information_sets.py',
            '--input', 'results\llm_daily_information_sets_v1.json',
            '--output', $full,
            '--model', $model,
            '--run-id', 'qwen25-full-stage2-v1',
            '--workers', '1',
            '--request-delay-seconds', "$requestDelaySeconds",
            '--seed-checkpoint', $seed
        )
        $scorer = Start-Process -FilePath $pythonExe -ArgumentList $arguments `
            -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        Write-Output "FULL_START cycle=$cycle pid=$($scorer.Id) records=$($state.Records) gpu_temp_c=$temperature"

        $thermalTrip = $false
        while (-not $scorer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $scorer.Refresh()
            $temperature = Get-GpuTemperatureC
            $state = Get-FullState
            Write-Output "THERMAL cycle=$cycle gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
            if ($temperature -ge $hardCeilingC) {
                Write-Output "THERMAL_STOP cycle=$cycle gpu_temp_c=$temperature records=$($state.Records)"
                Stop-Scorer $scorer
                Unload-LocalModel
                Set-BalancedPowerPlan
                $thermalTrip = $true
                break
            }
        }
        if ($thermalTrip) { $scorer = $null; continue }

        $scorer.WaitForExit()
        $scorer.Refresh()
        $exitCode = $scorer.ExitCode
        $scorer = $null
        $state = Get-FullState
        if ($null -ne $exitCode -and $exitCode -ne 0) {
            throw "Full inference failed: exit=$exitCode records=$($state.Records) stderr=$stderr"
        }
        if ($state.Records -ne $expectedRecords -or $state.Success -ne $expectedRecords `
                -or $state.Errors -ne 0 -or $state.Unique -ne $expectedRecords) {
            throw "Full inference incomplete: records=$($state.Records) success=$($state.Success) errors=$($state.Errors) unique=$($state.Unique)"
        }
    }

    Unload-LocalModel
    Set-BalancedPowerPlan
    Write-Output 'FULL_INFERENCE_VALIDATED records=2927 success=2927 errors=0 unique=2927'
    Invoke-PythonStep 'outcome-calibration' @(
        'executor\audit_llm_outcome_calibration.py', '--scores', $full,
        '--btc-bars', 'results\bybit_lifecycle_4h\BTCUSDT_1660348800000_1786492800000.json',
        '--output', $calibration
    )
    Invoke-PythonStep 'stage2-gate-evaluation' @(
        'executor\evaluate_llm_challenger_stage2.py', '--config', $config,
        '--stage1', $stage1, '--full-run', $full, '--calibration', $calibration,
        '--output', $stage2
    )
    Invoke-PythonStep 'regression-tests' @(
        '-m', 'unittest', 'discover', '-s', 'executor', '-p', 'test_*.py'
    )
    Invoke-PythonStep 'tech-freeze-verification' @(
        'executor\freeze_experiment.py', '--verify'
    )
    Write-Output 'QWEN25_STAGE2_COMPLETE'
}
finally {
    if ($null -ne $scorer) { Stop-Scorer $scorer }
    Remove-EmptyRedirectLogs -Directory $logDirectory
    Unload-LocalModel
    Set-BalancedPowerPlan
    Write-Output 'SAFETY_CLEANUP_COMPLETE power_plan=Balanced'
}
