param(
    [string]$Model = 'qwen2.5:7b',
    [string]$CandidateId = 'qwen25_7b',
    [string]$ModelArtifactStem = 'qwen2_5_7b',
    [string]$Config = 'configs\llm_qwen25_7b_challenger_v1_development.json',
    [switch]$DisableThinking
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDirectory = Join-Path $workspaceRoot 'runtime\logs\llm'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonExe = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$ollamaExe = if ($env:KLTN_OLLAMA_EXE) { $env:KLTN_OLLAMA_EXE } else { (Get-Command ollama -ErrorAction Stop).Source }
$ollamaServerRoot = if ($env:KLTN_OLLAMA_SERVER_ROOT) { $env:KLTN_OLLAMA_SERVER_ROOT } else { Split-Path -Parent $ollamaExe }
$model = $Model
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 5
$expectedRecords = 108
$requestDelaySeconds = 10
$sessionId = Get-Date -Format 'yyyyMMdd_HHmmss'
$scorer = $null
$failFastTriggered = $false

$runs = @(
    "results\llm_daily_reliability_${ModelArtifactStem}_run1_v1.json",
    "results\llm_daily_reliability_${ModelArtifactStem}_run2_v1.json"
)
$audit = "results\llm_daily_reliability_${ModelArtifactStem}_determinism_v1.json"
$gate = "results\llm_${CandidateId}_challenger_gate_v1.json"
$config = $Config

foreach ($path in @($repo, $pythonExe, $ollamaExe, (Join-Path $repo $config))) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path is missing: $path"
    }
}

function Set-BalancedPowerPlan {
    powercfg /setactive SCHEME_BALANCED | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to activate Windows Balanced'
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

function Invoke-ScoringRun {
    param([int]$RunNumber, [string]$RelativeOutput)
    $cycle = 0
    while ($true) {
        $state = Get-RunState $RelativeOutput
        if ($state.Errors -gt 0) {
            Write-Output "IRREVERSIBLE_SCHEMA_FAILURE run=$RunNumber records=$($state.Records) errors=$($state.Errors)"
            Stop-Scorer $script:scorer
            $script:scorer = $null
            Unload-LocalModel
            Set-BalancedPowerPlan
            $script:failFastTriggered = $true
            return
        }
        if ($state.Records -eq $expectedRecords) {
            if ($state.Unique -ne $expectedRecords) {
                throw "Run $RunNumber duplicate hash failure: unique=$($state.Unique)"
            }
            return
        }
        if ($state.Records -gt $expectedRecords -or $state.Unique -ne $state.Records) {
            throw "Run $RunNumber checkpoint invalid: records=$($state.Records) unique=$($state.Unique)"
        }

        $temperature = Get-GpuTemperatureC
        while ($temperature -gt $resumeAtC) {
            Write-Output "COOLDOWN run=$RunNumber gpu_temp_c=$temperature time=$(Get-Date -Format o)"
            Start-Sleep -Seconds $pollSeconds
            $temperature = Get-GpuTemperatureC
        }

        Remove-EmptyRedirectLogs -Directory $logDirectory
        $cycle += 1
        $stdout = Join-Path $logDirectory "${CandidateId}_gate_${sessionId}_run_${RunNumber}_cycle_${cycle}.stdout.log"
        $stderr = Join-Path $logDirectory "${CandidateId}_gate_${sessionId}_run_${RunNumber}_cycle_${cycle}.stderr.log"
        $arguments = @(
            'executor\score_llm_daily_information_sets.py',
            '--input', 'results\llm_daily_information_sets_v1.json',
            '--output', $RelativeOutput,
            '--model', $model,
            '--run-id', "${CandidateId}-stage1-run$RunNumber-v1",
            '--sample-per-year', '12',
            '--workers', '1',
            '--request-delay-seconds', "$requestDelaySeconds"
        )
        if ($DisableThinking) {
            $arguments += '--disable-thinking'
        }
        $script:scorer = Start-Process -FilePath $pythonExe -ArgumentList $arguments `
            -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        Write-Output "SCORING_START run=$RunNumber cycle=$cycle pid=$($script:scorer.Id) records=$($state.Records) gpu_temp_c=$temperature"

        $thermalTrip = $false
        $schemaTrip = $false
        while (-not $script:scorer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $script:scorer.Refresh()
            $temperature = Get-GpuTemperatureC
            $state = Get-RunState $RelativeOutput
            Write-Output "THERMAL run=$RunNumber cycle=$cycle gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
            if ($state.Errors -gt 0) {
                Write-Output "IRREVERSIBLE_SCHEMA_STOP run=$RunNumber cycle=$cycle records=$($state.Records) errors=$($state.Errors)"
                Stop-Scorer $script:scorer
                Unload-LocalModel
                Set-BalancedPowerPlan
                $script:failFastTriggered = $true
                $schemaTrip = $true
                break
            }
            if ($temperature -ge $hardCeilingC) {
                Write-Output "THERMAL_STOP run=$RunNumber cycle=$cycle gpu_temp_c=$temperature records=$($state.Records)"
                Stop-Scorer $script:scorer
                Unload-LocalModel
                Set-BalancedPowerPlan
                $thermalTrip = $true
                break
            }
        }
        if ($schemaTrip) {
            $script:scorer = $null
            return
        }
        if ($thermalTrip) {
            $script:scorer = $null
            continue
        }

        $script:scorer.WaitForExit()
        $script:scorer.Refresh()
        $exitCode = $script:scorer.ExitCode
        $script:scorer = $null
        $state = Get-RunState $RelativeOutput
        if ($null -ne $exitCode -and $exitCode -ne 0) {
            throw "Run $RunNumber failed: exit=$exitCode records=$($state.Records) stderr=$stderr"
        }
        if ($state.Records -ne $expectedRecords -or $state.Unique -ne $expectedRecords) {
            throw "Run $RunNumber incomplete: records=$($state.Records) unique=$($state.Unique)"
        }
        return
    }
}

function Invoke-PythonStep {
    param([string]$Label, [string[]]$Arguments)
    $temperature = Get-GpuTemperatureC
    if ($temperature -ge $hardCeilingC) {
        throw "$Label refused at GPU temperature ${temperature}C"
    }
    Write-Output "STEP_START label=$Label gpu_temp_c=$temperature"
    & $pythonExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
    Write-Output "STEP_COMPLETE label=$Label"
}

Set-Location -LiteralPath $repo
Set-BalancedPowerPlan
$env:PYTHONPATH = "$(Join-Path $repo 'executor');$(Join-Path $repo '.venv\Lib\site-packages')"

try {
    for ($index = 0; $index -lt $runs.Count; $index += 1) {
        Invoke-ScoringRun ($index + 1) $runs[$index]
        if ($failFastTriggered) {
            Invoke-PythonStep 'fail-fast-gate-evaluation' @(
                'executor\evaluate_llm_challenger_fail_fast.py', '--config', $config,
                '--partial-run', $runs[$index], '--output', $gate
            )
            break
        }
        Unload-LocalModel
        Set-BalancedPowerPlan
        $state = Get-RunState $runs[$index]
        Write-Output "RUN_COMPLETE run=$($index + 1) records=$($state.Records) success=$($state.Success) errors=$($state.Errors)"
    }

    if (-not $failFastTriggered) {
        Invoke-PythonStep 'determinism-audit' @(
            'executor\audit_llm_determinism.py', '--left', $runs[0], '--right', $runs[1],
            '--output', $audit
        )
        Invoke-PythonStep 'predeclared-gate-evaluation' @(
            'executor\evaluate_llm_challenger_gate.py', '--config', $config, '--audit', $audit,
            '--left', $runs[0], '--right', $runs[1], '--output', $gate
        )
    }
    Invoke-PythonStep 'regression-tests' @(
        '-m', 'unittest', 'discover', '-s', 'executor', '-p', 'test_*.py'
    )
    Write-Output "CHALLENGER_STAGE1_COMPLETE candidate=$CandidateId"
}
finally {
    if ($null -ne $scorer) { Stop-Scorer $scorer }
    Remove-EmptyRedirectLogs -Directory $logDirectory
    Unload-LocalModel
    Set-BalancedPowerPlan
    Write-Output 'SAFETY_CLEANUP_COMPLETE power_plan=Balanced'
}
