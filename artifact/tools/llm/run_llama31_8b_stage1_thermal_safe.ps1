param(
    [string]$RunRoot = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'runtime\llama31_8b_challenger')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourceExecutor = Join-Path $workspaceRoot 'executor'
$pythonExe = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$model = 'llama3.1:8b'
$candidateId = 'llama31_8b'
$modelArtifactStem = 'llama31_8b'
$config = Join-Path $RunRoot 'configs\llm_llama31_8b_challenger_v1_development.json'
$inputArtifact = Join-Path $RunRoot 'results\llm_daily_information_sets_v1.json'
$logDirectory = Join-Path $RunRoot 'logs'
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 5
$expectedRecords = 108
$requestDelaySeconds = 10
$sessionId = Get-Date -Format 'yyyyMMdd_HHmmss'
$scorer = $null
$failFastTriggered = $false

$runs = @(
    (Join-Path $RunRoot "results\llm_daily_reliability_${modelArtifactStem}_run1_v1.json"),
    (Join-Path $RunRoot "results\llm_daily_reliability_${modelArtifactStem}_run2_v1.json")
)
$audit = Join-Path $RunRoot "results\llm_daily_reliability_${modelArtifactStem}_determinism_v1.json"
$gate = Join-Path $RunRoot "results\llm_${candidateId}_challenger_gate_v1.json"

foreach ($path in @($RunRoot, $sourceExecutor, $pythonExe, $config, $inputArtifact)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

function Set-BalancedPowerPlan {
    $activeScheme = powercfg /getactivescheme
    if ($LASTEXITCODE -eq 0 -and $activeScheme -match '381b4222-f694-41f0-9685-ff5bb260df2e') {
        return
    }
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
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{ Records = 0; Success = 0; Errors = 0; Unique = 0 }
    }
    $payload = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
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
    Stop-Process -Id $Process.Id -Force -ErrorAction Stop
    $Process.WaitForExit(10000) | Out-Null
}

function Unload-LocalModel {
    try {
        $body = @{ model = $model; prompt = ''; stream = $false; keep_alive = 0 } | ConvertTo-Json
        Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/generate' -Method Post `
            -ContentType 'application/json' -Body $body | Out-Null
    }
    catch { Write-Output "OLLAMA_STOP_WARNING=$($_.Exception.Message)" }
}

function Invoke-ScoringRun {
    param([int]$RunNumber, [string]$Output)
    $cycle = 0
    while ($true) {
        $state = Get-RunState $Output
        if ($state.Errors -gt 0) {
            Write-Output "IRREVERSIBLE_SCHEMA_FAILURE run=$RunNumber records=$($state.Records) errors=$($state.Errors)"
            $script:failFastTriggered = $true
            return
        }
        if ($state.Records -eq $expectedRecords) {
            if ($state.Unique -ne $expectedRecords) { throw "Run $RunNumber duplicate hash failure" }
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
        $stdout = Join-Path $logDirectory "${candidateId}_gate_${sessionId}_run_${RunNumber}_cycle_${cycle}.stdout.log"
        $stderr = Join-Path $logDirectory "${candidateId}_gate_${sessionId}_run_${RunNumber}_cycle_${cycle}.stderr.log"
        $arguments = @(
            (Join-Path $sourceExecutor 'score_llm_daily_information_sets.py'),
            '--input', $inputArtifact,
            '--output', $Output,
            '--model', $model,
            '--run-id', "${candidateId}-stage1-run$RunNumber-v1",
            '--sample-per-year', '12',
            '--workers', '1',
            '--request-delay-seconds', "$requestDelaySeconds"
        )
        $script:scorer = Start-Process -FilePath $pythonExe -ArgumentList $arguments `
            -WorkingDirectory $RunRoot -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        Write-Output "SCORING_START run=$RunNumber cycle=$cycle pid=$($script:scorer.Id) records=$($state.Records) gpu_temp_c=$temperature"

        $thermalTrip = $false
        while (-not $script:scorer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $script:scorer.Refresh()
            $temperature = Get-GpuTemperatureC
            $state = Get-RunState $Output
            Write-Output "THERMAL run=$RunNumber cycle=$cycle gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
            if ($state.Errors -gt 0) {
                Write-Output "IRREVERSIBLE_SCHEMA_STOP run=$RunNumber records=$($state.Records) errors=$($state.Errors)"
                Stop-Scorer $script:scorer
                Unload-LocalModel
                Set-BalancedPowerPlan
                $script:failFastTriggered = $true
                $script:scorer = $null
                return
            }
            if ($temperature -ge $hardCeilingC) {
                Write-Output "THERMAL_STOP run=$RunNumber gpu_temp_c=$temperature records=$($state.Records)"
                Stop-Scorer $script:scorer
                Unload-LocalModel
                Set-BalancedPowerPlan
                $thermalTrip = $true
                break
            }
        }
        if ($thermalTrip) { $script:scorer = $null; continue }

        $script:scorer.WaitForExit()
        $script:scorer.Refresh()
        $exitCode = $script:scorer.ExitCode
        $script:scorer = $null
        $state = Get-RunState $Output
        if ($exitCode -ne 0) { throw "Run $RunNumber failed: exit=$exitCode stderr=$stderr" }
        if ($state.Records -ne $expectedRecords -or $state.Unique -ne $expectedRecords) {
            throw "Run $RunNumber incomplete: records=$($state.Records) unique=$($state.Unique)"
        }
        return
    }
}

function Invoke-PythonStep {
    param([string]$Label, [string[]]$Arguments)
    $temperature = Get-GpuTemperatureC
    if ($temperature -ge $hardCeilingC) { throw "$Label refused at GPU temperature ${temperature}C" }
    Write-Output "STEP_START label=$Label gpu_temp_c=$temperature"
    & $pythonExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
    Write-Output "STEP_COMPLETE label=$Label"
}

Set-BalancedPowerPlan
$env:PYTHONPATH = $sourceExecutor
$env:PYTHONDONTWRITEBYTECODE = '1'

try {
    for ($index = 0; $index -lt $runs.Count; $index += 1) {
        Invoke-ScoringRun ($index + 1) $runs[$index]
        if ($failFastTriggered) {
            Invoke-PythonStep 'fail-fast-gate-evaluation' @(
                (Join-Path $sourceExecutor 'evaluate_llm_challenger_fail_fast.py'),
                '--config', $config, '--partial-run', $runs[$index], '--output', $gate
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
            (Join-Path $sourceExecutor 'audit_llm_determinism.py'),
            '--left', $runs[0], '--right', $runs[1], '--output', $audit
        )
        Invoke-PythonStep 'predeclared-gate-evaluation' @(
            (Join-Path $sourceExecutor 'evaluate_llm_challenger_gate.py'),
            '--config', $config, '--audit', $audit, '--left', $runs[0],
            '--right', $runs[1], '--output', $gate
        )
        Invoke-PythonStep 'focused-regression-tests' @(
            '-m', 'unittest',
            'test_score_llm_daily_information_sets',
            'test_audit_llm_determinism',
            'test_evaluate_llm_challenger_gate',
            'test_evaluate_llm_challenger_fail_fast'
        )
    }
    Write-Output "CHALLENGER_STAGE1_COMPLETE candidate=$candidateId gate=$gate"
}
finally {
    if ($null -ne $scorer) { Stop-Scorer $scorer }
    Remove-EmptyRedirectLogs -Directory $logDirectory
    Unload-LocalModel
    Set-BalancedPowerPlan
    Write-Output 'SAFETY_CLEANUP_COMPLETE power_plan=Balanced'
}
