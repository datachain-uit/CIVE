$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDirectory = Join-Path $workspaceRoot 'runtime\logs\llm'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonExe = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$ollamaExe = if ($env:KLTN_OLLAMA_EXE) { $env:KLTN_OLLAMA_EXE } else { (Get-Command ollama -ErrorAction Stop).Source }
$ollamaServerRoot = if ($env:KLTN_OLLAMA_SERVER_ROOT) { $env:KLTN_OLLAMA_SERVER_ROOT } else { Split-Path -Parent $ollamaExe }
$checkpoint = Join-Path $repo 'results\llm_daily_full_llama3_repeat2.json'
$model = 'llama3:latest'
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 1
$expectedRecords = 2927
$scorer = $null
$sessionId = Get-Date -Format 'yyyyMMdd_HHmmss'

foreach ($path in @($repo, $pythonExe, $ollamaExe, $checkpoint)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path is missing: $path"
    }
}

function Set-BalancedPowerPlan {
    powercfg /setactive SCHEME_BALANCED | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to set the Windows Balanced power plan'
    }
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

function Stop-Scorer {
    param([System.Diagnostics.Process]$Process)
    if ($null -ne $Process) {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            $live = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
            if ($live -and $live.ProcessName -ne 'python') {
                throw "Scorer PID $($Process.Id) changed identity to $($live.ProcessName)"
            }
            if ($live) {
                Stop-Process -Id $Process.Id -Force -ErrorAction Stop
                $Process.WaitForExit(10000) | Out-Null
            }
        }
    }
}

function Unload-LocalModel {
    try {
        & $ollamaExe stop $model | Out-Null
    }
    catch {
        Write-Output "OLLAMA_STOP_WARNING=$($_.Exception.Message)"
    }
    Start-Sleep -Seconds 2
    $servers = @(Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue)
    foreach ($server in $servers) {
        if (-not $server.Path.StartsWith($ollamaServerRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to stop unexpected llama-server path: $($server.Path)"
        }
        Stop-Process -Id $server.Id -Force -ErrorAction Stop
    }
}

function Read-Checkpoint {
    $payload = Get-Content -LiteralPath $checkpoint -Raw | ConvertFrom-Json
    return [pscustomobject]@{
        Payload = $payload
        Records = @($payload.records).Count
        Success = [int]$payload.summary.success
        Errors = [int]$payload.summary.errors
        UniqueHashes = @($payload.records.content_hash | Sort-Object -Unique).Count
        LastDate = if (@($payload.records).Count -gt 0) { $payload.records[-1].information_date } else { 'none' }
    }
}

function Invoke-PythonStep {
    param(
        [string]$Label,
        [string[]]$Arguments
    )
    $temperature = Get-GpuTemperatureC
    if ($temperature -ge $hardCeilingC) {
        throw "$Label refused at GPU temperature ${temperature}C"
    }
    Write-Output "STEP_START label=$Label gpu_temp_c=$temperature time=$(Get-Date -Format o)"
    & $pythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
    Write-Output "STEP_COMPLETE label=$Label time=$(Get-Date -Format o)"
}

Set-Location -LiteralPath $repo
Set-BalancedPowerPlan
$env:PYTHONPATH = Join-Path $repo '.venv\Lib\site-packages'

try {
    $cycle = 0
    while ($true) {
        $state = Read-Checkpoint
        if ($state.Records -eq $expectedRecords -and $state.Success -eq $expectedRecords -and $state.Errors -eq 0) {
            break
        }
        if ($state.Records -gt $expectedRecords -or $state.UniqueHashes -ne $state.Records) {
            throw "Checkpoint invalid: records=$($state.Records) unique=$($state.UniqueHashes)"
        }

        $temperature = Get-GpuTemperatureC
        while ($temperature -gt $resumeAtC) {
            Write-Output "COOLDOWN gpu_temp_c=$temperature resume_at_c=$resumeAtC time=$(Get-Date -Format o)"
            Start-Sleep -Seconds $pollSeconds
            $temperature = Get-GpuTemperatureC
        }

        Remove-EmptyRedirectLogs -Directory $logDirectory
        $cycle += 1
        $stdout = Join-Path $logDirectory "llm_repeat2_${sessionId}_cycle_${cycle}.stdout.log"
        $stderr = Join-Path $logDirectory "llm_repeat2_${sessionId}_cycle_${cycle}.stderr.log"
        if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) {
            throw "Cycle log already exists for cycle $cycle"
        }
        $arguments = @(
            'executor\score_llm_daily_information_sets.py',
            '--input', 'results\llm_daily_information_sets_v1.json',
            '--output', 'results\llm_daily_full_llama3_repeat2.json',
            '--model', $model,
            '--run-id', 'full-repeat2-consensus-v1',
            '--workers', '1',
            '--request-delay-seconds', '10',
            '--seed-checkpoint', 'results\llm_daily_reliability_llama3_repeat108.json'
        )
        $scorer = Start-Process -FilePath $pythonExe -ArgumentList $arguments `
            -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        Write-Output "INFERENCE_START cycle=$cycle pid=$($scorer.Id) records=$($state.Records) gpu_temp_c=$temperature time=$(Get-Date -Format o)"

        $thermalTrip = $false
        while (-not $scorer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $scorer.Refresh()
            $temperature = Get-GpuTemperatureC
            $state = Read-Checkpoint
            Write-Output "THERMAL cycle=$cycle pid=$($scorer.Id) gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors) time=$(Get-Date -Format o)"
            if ($temperature -ge $hardCeilingC) {
                Write-Output "THERMAL_STOP cycle=$cycle gpu_temp_c=$temperature ceiling_c=$hardCeilingC records=$($state.Records)"
                Stop-Scorer -Process $scorer
                Unload-LocalModel
                Set-BalancedPowerPlan
                $thermalTrip = $true
                break
            }
        }

        if ($thermalTrip) {
            $scorer = $null
            continue
        }
        $scorer.Refresh()
        $exitCode = $scorer.ExitCode
        $scorer = $null
        $state = Read-Checkpoint
        if ($exitCode -ne 0) {
            throw "Inference exited unexpectedly: exit=$exitCode records=$($state.Records) errors=$($state.Errors) stderr=$stderr"
        }
        if ($state.Records -ne $expectedRecords -or $state.Success -ne $expectedRecords -or $state.Errors -ne 0) {
            throw "Inference exited incomplete: records=$($state.Records) success=$($state.Success) errors=$($state.Errors)"
        }
    }

    Unload-LocalModel
    Set-BalancedPowerPlan
    $final = Read-Checkpoint
    if ($final.UniqueHashes -ne $expectedRecords) {
        throw "Final inference hash-set invalid: unique=$($final.UniqueHashes)"
    }
    Write-Output "INFERENCE_VALIDATED records=$($final.Records) success=$($final.Success) errors=$($final.Errors) unique_hashes=$($final.UniqueHashes)"

    Invoke-PythonStep 'determinism-audit' @(
        'executor\audit_llm_determinism.py', '--left', 'results\llm_daily_full_llama3_development.json',
        '--right', 'results\llm_daily_full_llama3_repeat2.json', '--output',
        'results\llm_daily_full_llama3_repeat2_determinism.json'
    )
    Invoke-PythonStep 'dual-run-consensus' @(
        'executor\build_llm_dual_run_consensus.py', '--left',
        'results\llm_daily_full_llama3_development.json', '--right',
        'results\llm_daily_full_llama3_repeat2.json', '--output',
        'results\llm_daily_dual_run_consensus_v1.json'
    )
    Invoke-PythonStep 'lifecycle-adapter' @(
        'executor\llm_lifecycle_adapter.py', '--scores',
        'results\llm_daily_dual_run_consensus_v1.json', '--lifecycle-manifest',
        'results\bybit_lifecycle_universe.json', '--output',
        'results\llm_daily_dual_run_consensus_v1_targets.json'
    )
    Invoke-PythonStep 'consensus-backtest' @(
        'executor\llm_bybit_lifecycle_execution.py', '--scores',
        'results\llm_daily_dual_run_consensus_v1.json', '--lifecycle-manifest',
        'results\bybit_lifecycle_universe.json', '--output',
        'results\llm_bybit_lifecycle_dual_run_consensus_v1_development.json',
        '--daily-cache-dir', 'results\bybit_lifecycle_daily', '--four-h-cache-dir',
        'results\bybit_lifecycle_4h', '--funding-cache-dir',
        'results\bybit_lifecycle_funding', '--stop-atr', '3', '--trail-atr', '4',
        '--gross-leverage', '1', '--workers', '1'
    )
    Invoke-PythonStep 'consensus-calibration' @(
        'executor\audit_llm_outcome_calibration.py', '--scores',
        'results\llm_daily_dual_run_consensus_v1.json', '--btc-bars',
        'results\bybit_lifecycle_4h\BTCUSDT_1660348800000_1786492800000.json',
        '--output', 'results\llm_outcome_calibration_dual_run_consensus_v1_development.json'
    )
    Invoke-PythonStep 'regression-tests' @(
        '-m', 'unittest', 'discover', '-s', 'executor', '-p', 'test_*.py'
    )
    Invoke-PythonStep 'tech-freeze-verification' @(
        'executor\freeze_experiment.py', '--verify'
    )
    Write-Output 'POSTPROCESS_COMPLETE'
}
finally {
    if ($null -ne $scorer) {
        Stop-Scorer -Process $scorer
    }
    Remove-EmptyRedirectLogs -Directory $logDirectory
    Unload-LocalModel
    Set-BalancedPowerPlan
    Write-Output 'SAFETY_CLEANUP_COMPLETE power_plan=Balanced'
}
