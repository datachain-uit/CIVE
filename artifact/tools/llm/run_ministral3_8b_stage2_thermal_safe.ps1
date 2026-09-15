param(
    [string]$RunRoot = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'runtime\ministral3_8b_challenger'),
    [string]$InputArtifactPath = '',
    [string]$ConfigPath = '',
    [string]$Stage1GatePath = '',
    [string]$SeedCheckpointPath = '',
    [string]$ScorerScriptPath = '',
    [string]$Stage2EvaluatorPath = '',
    [string]$OutputTag = 'v1',
    [int]$ExpectedRecords = 2927,
    [int]$RequestDelaySeconds = 10
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourceExecutor = Join-Path $workspaceRoot 'executor'
$btcBars = Join-Path $workspaceRoot 'results\bybit_lifecycle_4h\BTCUSDT_1660348800000_1786492800000.json'
$pythonExe = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$model = 'ministral-3:8b'
$candidateId = 'ministral3_8b'
$config = if ($ConfigPath) { $ConfigPath } else { Join-Path $RunRoot 'configs\llm_ministral3_8b_challenger_v1_development.json' }
$stage1Gate = if ($Stage1GatePath) { $Stage1GatePath } else { Join-Path $RunRoot 'results\llm_ministral3_8b_challenger_gate_v1.json' }
$seedCheckpoint = if ($SeedCheckpointPath) { $SeedCheckpointPath } else { Join-Path $RunRoot 'results\llm_daily_reliability_ministral3_8b_run1_v1.json' }
$inputArtifact = if ($InputArtifactPath) { $InputArtifactPath } else { Join-Path $RunRoot 'results\llm_daily_information_sets_v1.json' }
$scorerScript = if ($ScorerScriptPath) { $ScorerScriptPath } else { Join-Path $sourceExecutor 'score_llm_daily_information_sets.py' }
$stage2Evaluator = if ($Stage2EvaluatorPath) { $Stage2EvaluatorPath } else { Join-Path $sourceExecutor 'evaluate_llm_challenger_stage2.py' }
$full = Join-Path $RunRoot "results\llm_daily_full_ministral3_8b_${OutputTag}_development.json"
$calibration = Join-Path $RunRoot "results\llm_outcome_calibration_ministral3_8b_${OutputTag}_development.json"
$stage2 = Join-Path $RunRoot "results\llm_ministral3_8b_challenger_stage2_${OutputTag}.json"
$logDirectory = Join-Path $RunRoot 'logs'
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 5
$expectedRecords = $ExpectedRecords
$requestDelaySeconds = $RequestDelaySeconds
$sessionId = Get-Date -Format 'yyyyMMdd_HHmmss'
$scorer = $null

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
foreach ($path in @($RunRoot, $sourceExecutor, $btcBars, $pythonExe, $config, $stage1Gate, $seedCheckpoint, $inputArtifact, $scorerScript, $stage2Evaluator)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}

function Get-ActivePowerScheme {
    $scheme = powercfg /getactivescheme
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read active Windows power scheme' }
    return [string]$scheme
}

function Assert-BalancedPowerPlan {
    $scheme = Get-ActivePowerScheme
    if ($scheme -notmatch '381b4222-f694-41f0-9685-ff5bb260df2e') {
        throw "Heavy inference requires Windows Balanced; active scheme: $scheme"
    }
}

function Try-RestoreBalancedPowerPlan {
    try {
        $scheme = Get-ActivePowerScheme
        if ($scheme -match '381b4222-f694-41f0-9685-ff5bb260df2e') { return }
        powercfg /setactive SCHEME_BALANCED | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Output 'BALANCED_RESTORE_WARNING permission_denied' }
    }
    catch { Write-Output "BALANCED_RESTORE_WARNING=$($_.Exception.Message)" }
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
    if (-not (Test-Path -LiteralPath $full)) {
        return [pscustomobject]@{ Records = 0; Success = 0; Errors = 0; Unique = 0 }
    }
    $payload = Get-Content -LiteralPath $full -Raw | ConvertFrom-Json
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

function Invoke-PythonStep {
    param([string]$Label, [string[]]$Arguments)
    $temperature = Get-GpuTemperatureC
    if ($temperature -ge $hardCeilingC) { throw "$Label refused at GPU temperature ${temperature}C" }
    Write-Output "STEP_START label=$Label gpu_temp_c=$temperature"
    & $pythonExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
    Write-Output "STEP_COMPLETE label=$Label"
}

$stage1Payload = Get-Content -LiteralPath $stage1Gate -Raw | ConvertFrom-Json
if (-not $stage1Payload.passed) { throw 'Stage 1 did not authorize Stage 2' }
$configPayload = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
$inputHash = (Get-FileHash -Algorithm SHA256 $inputArtifact).Hash.ToLowerInvariant()
if ($inputHash -ne $configPayload.frozen_input_contract.sha256) { throw 'Frozen input hash mismatch' }
if (-not (Test-Path -LiteralPath $full)) {
    [System.IO.File]::Copy($seedCheckpoint, $full, $false)
    Write-Output "FULL_CHECKPOINT_SEEDED source=$seedCheckpoint output=$full"
}

Assert-BalancedPowerPlan
$env:PYTHONPATH = $sourceExecutor
$env:PYTHONDONTWRITEBYTECODE = '1'

try {
    $cycle = 0
    while ($true) {
        $state = Get-FullState
        if ($state.Errors -gt 0) {
            throw "Irreversible Stage 2 operational/schema failure: records=$($state.Records) errors=$($state.Errors)"
        }
        if ($state.Records -eq $expectedRecords) {
            if ($state.Success -ne $expectedRecords -or $state.Unique -ne $expectedRecords) {
                throw "Completed full checkpoint invalid: success=$($state.Success) unique=$($state.Unique)"
            }
            break
        }
        if ($state.Records -gt $expectedRecords -or $state.Unique -ne $state.Records) {
            throw "Full checkpoint invalid: records=$($state.Records) unique=$($state.Unique)"
        }

        Assert-BalancedPowerPlan
        $temperature = Get-GpuTemperatureC
        while ($temperature -gt $resumeAtC) {
            Write-Output "COOLDOWN gpu_temp_c=$temperature records=$($state.Records)"
            Start-Sleep -Seconds $pollSeconds
            $temperature = Get-GpuTemperatureC
        }

        Remove-EmptyRedirectLogs -Directory $logDirectory
        $cycle += 1
        $stdout = Join-Path $logDirectory "${candidateId}_stage2_${sessionId}_cycle_${cycle}.stdout.log"
        $stderr = Join-Path $logDirectory "${candidateId}_stage2_${sessionId}_cycle_${cycle}.stderr.log"
        $arguments = @(
            $scorerScript,
            '--input', $inputArtifact,
            '--output', $full,
            '--model', $model,
            '--run-id', "${candidateId}-full-stage2-$OutputTag",
            '--workers', '1',
            '--request-delay-seconds', "$requestDelaySeconds"
        )
        $script:scorer = Start-Process -FilePath $pythonExe -ArgumentList $arguments `
            -WorkingDirectory $RunRoot -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        Write-Output "FULL_START cycle=$cycle pid=$($script:scorer.Id) records=$($state.Records) gpu_temp_c=$temperature"

        $thermalTrip = $false
        while (-not $script:scorer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $script:scorer.Refresh()
            try {
                Assert-BalancedPowerPlan
            }
            catch {
                Write-Output "POWER_PLAN_STOP cycle=$cycle records=$($state.Records) reason=$($_.Exception.Message)"
                Stop-Scorer $script:scorer
                Unload-LocalModel
                $script:scorer = $null
                throw
            }
            $temperature = Get-GpuTemperatureC
            $state = Get-FullState
            Write-Output "THERMAL cycle=$cycle gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
            if ($state.Errors -gt 0) {
                Write-Output "IRREVERSIBLE_SCHEMA_STOP cycle=$cycle records=$($state.Records) errors=$($state.Errors)"
                Stop-Scorer $script:scorer
                Unload-LocalModel
                $script:scorer = $null
                throw 'Stage 2 stopped after first operational/schema error'
            }
            if ($temperature -ge $hardCeilingC) {
                Write-Output "THERMAL_STOP cycle=$cycle gpu_temp_c=$temperature records=$($state.Records)"
                Stop-Scorer $script:scorer
                Unload-LocalModel
                $script:scorer = $null
                $thermalTrip = $true
                break
            }
        }
        if ($thermalTrip) { continue }

        $script:scorer.WaitForExit()
        $script:scorer.Refresh()
        $exitCode = $script:scorer.ExitCode
        $script:scorer = $null
        $state = Get-FullState
        if ($null -ne $exitCode -and $exitCode -ne 0) {
            throw "Full inference failed: exit=$exitCode stderr=$stderr"
        }
        if ($state.Records -ne $expectedRecords -or $state.Success -ne $expectedRecords `
                -or $state.Errors -ne 0 -or $state.Unique -ne $expectedRecords) {
            throw "Full inference incomplete: records=$($state.Records) success=$($state.Success) errors=$($state.Errors) unique=$($state.Unique)"
        }
    }

    Unload-LocalModel
    Write-Output "FULL_INFERENCE_VALIDATED candidate=$candidateId records=$expectedRecords success=$expectedRecords errors=0 unique=$expectedRecords"
    Invoke-PythonStep 'outcome-calibration' @(
        (Join-Path $sourceExecutor 'audit_llm_outcome_calibration.py'),
        '--scores', $full, '--btc-bars', $btcBars, '--output', $calibration
    )
    Invoke-PythonStep 'stage2-gate-evaluation' @(
        $stage2Evaluator,
        '--config', $config, '--stage1', $stage1Gate, '--full-run', $full,
        '--calibration', $calibration, '--output', $stage2
    )
    Invoke-PythonStep 'focused-regression-tests' @(
        '-m', 'unittest',
        'test_score_llm_daily_information_sets',
        'test_audit_llm_outcome_calibration',
        'test_evaluate_llm_challenger_stage2'
    )
    Write-Output "CHALLENGER_STAGE2_COMPLETE candidate=$candidateId gate=$stage2"
}
finally {
    if ($null -ne $scorer) { Stop-Scorer $scorer }
    Remove-EmptyRedirectLogs -Directory $logDirectory
    Unload-LocalModel
    Try-RestoreBalancedPowerPlan
    $scheme = Get-ActivePowerScheme
    Write-Output "SAFETY_CLEANUP_COMPLETE active_power_scheme=$scheme"
}
