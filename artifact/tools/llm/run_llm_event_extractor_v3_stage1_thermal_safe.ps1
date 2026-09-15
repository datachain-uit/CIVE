param(
    [string]$RunRoot = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'runtime\ministral3_8b_challenger'),
    [string]$ConfigFile = 'llm_event_extractor_v3_stage1_predeclared.json',
    [string]$OutputTag = 'v3',
    [string]$ScorerFile = 'score_llm_event_extractor_v3.py',
    [string]$AuditFile = 'evaluate_llm_event_extractor_v3_stage1.py',
    [string]$Model = 'ministral-3:8b',
    [int]$RequestDelaySeconds = 10
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$config = Join-Path (Join-Path $RunRoot 'configs') $ConfigFile
$inputArtifact = Join-Path $workspace 'paper\input\results\llm\v3\llm_event_extractor_stage1_sample_v3_frozen.json'
$scorerScript = Join-Path (Join-Path $workspace 'tools\llm') $ScorerFile
$auditScript = Join-Path (Join-Path $workspace 'tools\llm') $AuditFile
$failFastScript = Join-Path $workspace 'tools\llm\evaluate_llm_event_extractor_v3_fail_fast.py'
$results = Join-Path $RunRoot 'results'
$logs = Join-Path $RunRoot 'logs'
$run1 = Join-Path $results "llm_event_extractor_${OutputTag}_stage1_run1.json"
$run2 = Join-Path $results "llm_event_extractor_${OutputTag}_stage1_run2.json"
$gate = Join-Path $results "llm_event_extractor_${OutputTag}_stage1_gate.json"
$model = $Model
$expected = 114
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 5
$session = Get-Date -Format 'yyyyMMdd_HHmmss'
$producer = $null
$runPassed = $false

foreach ($path in @($workspace, $RunRoot, $python, $config, $inputArtifact, $scorerScript, $auditScript, $failFastScript)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}
New-Item -ItemType Directory -Force -Path $results, $logs | Out-Null

function Set-BalancedPlan {
    $active = powercfg /getactivescheme
    if ($LASTEXITCODE -eq 0 -and $active -match '381b4222-f694-41f0-9685-ff5bb260df2e') { return }
    powercfg /setactive SCHEME_BALANCED | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to activate Windows Balanced' }
}

function Test-BalancedPlan {
    $active = powercfg /getactivescheme
    return $LASTEXITCODE -eq 0 -and $active -match '381b4222-f694-41f0-9685-ff5bb260df2e'
}

function Get-GpuTemperatureC {
    $raw = & nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits
    $value = 0
    if ($LASTEXITCODE -ne 0 -or @($raw).Count -ne 1 -or
        -not [int]::TryParse(([string]$raw).Trim(), [ref]$value)) {
        throw 'Cannot read exactly one NVIDIA GPU temperature; failing closed'
    }
    return $value
}

function Get-State([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{ Records = 0; Success = 0; Errors = 0 }
    }
    $payload = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    return [pscustomobject]@{
        Records = @($payload.records).Count
        Success = [int]$payload.summary.success
        Errors = [int]$payload.summary.errors
    }
}

function Stop-Producer {
    if ($null -eq $script:producer) { return }
    $script:producer.Refresh()
    if (-not $script:producer.HasExited) {
        Stop-Process -Id $script:producer.Id -Force
        $script:producer.WaitForExit(10000) | Out-Null
    }
    $script:producer = $null
}

function Unload-Model {
    try {
        $body = @{ model = $model; prompt = ''; stream = $false; keep_alive = 0 } | ConvertTo-Json
        Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/generate' -Method Post `
            -ContentType 'application/json' -Body $body -TimeoutSec 30 | Out-Null
    }
    catch { Write-Output "OLLAMA_UNLOAD_WARNING=$($_.Exception.Message)" }
}

function Wait-UntilCool([int]$RunNumber) {
    $temperature = Get-GpuTemperatureC
    while ($temperature -gt $resumeAtC) {
        Write-Output "COOLDOWN run=$RunNumber gpu_temp_c=$temperature time=$(Get-Date -Format o)"
        Start-Sleep -Seconds $pollSeconds
        $temperature = Get-GpuTemperatureC
    }
}

function Invoke-Run([int]$RunNumber, [string]$Output) {
    $cycle = 0
    while ($true) {
        $state = Get-State $Output
        if ($state.Errors -gt 0) { $script:runPassed = $false; return }
        if ($state.Records -eq $expected -and $state.Success -eq $expected) {
            $script:runPassed = $true
            return
        }
        if ($state.Records -gt $expected) { throw "Run $RunNumber checkpoint exceeds expected records" }
        Wait-UntilCool $RunNumber
        Set-BalancedPlan
        Remove-EmptyRedirectLogs -Directory $logs
        $cycle += 1
        $stdout = Join-Path $logs "event_v3_${session}_run${RunNumber}_cycle${cycle}.stdout.log"
        $stderr = Join-Path $logs "event_v3_${session}_run${RunNumber}_cycle${cycle}.stderr.log"
        $arguments = @(
            $scorerScript, '--config', $config, '--input', $inputArtifact, '--output', $Output,
            '--run-id', "event-$OutputTag-stage1-run$RunNumber", '--request-delay-seconds', "$RequestDelaySeconds"
        )
        $script:producer = Start-Process -FilePath $python -ArgumentList $arguments `
            -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        Write-Output "SCORING_START run=$RunNumber cycle=$cycle pid=$($script:producer.Id) records=$($state.Records)"
        $thermalTrip = $false
        while (-not $script:producer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $script:producer.Refresh()
            $temperature = Get-GpuTemperatureC
            $state = Get-State $Output
            Write-Output "THERMAL run=$RunNumber cycle=$cycle gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
            if (-not (Test-BalancedPlan)) {
                Write-Output "POWER_PLAN_RESTORE run=$RunNumber cycle=$cycle records=$($state.Records)"
                try {
                    Set-BalancedPlan
                    Write-Output "POWER_PLAN_RESTORED run=$RunNumber cycle=$cycle records=$($state.Records)"
                }
                catch {
                    Write-Output "POWER_PLAN_STOP run=$RunNumber cycle=$cycle records=$($state.Records)"
                    Stop-Producer
                    Unload-Model
                    throw 'Active power plan changed away from Balanced and could not be restored'
                }
            }
            if ($state.Errors -gt 0) {
                Stop-Producer
                Unload-Model
                Set-BalancedPlan
                $script:runPassed = $false
                return
            }
            if ($temperature -ge $hardCeilingC) {
                Write-Output "THERMAL_STOP run=$RunNumber cycle=$cycle gpu_temp_c=$temperature records=$($state.Records)"
                Stop-Producer
                Unload-Model
                Set-BalancedPlan
                $thermalTrip = $true
                break
            }
        }
        if ($thermalTrip) { continue }
        $script:producer.WaitForExit()
        $script:producer.Refresh()
        $exitCode = $script:producer.ExitCode
        $script:producer = $null
        $finalState = Get-State $Output
        if ($exitCode -ne 0 -and -not ($finalState.Records -eq $expected -and $finalState.Success -eq $expected -and $finalState.Errors -eq 0)) {
            $tail = if (Test-Path $stderr) { Get-Content $stderr -Tail 20 | Out-String } else { '' }
            throw "Run $RunNumber scorer failed exit=$exitCode stderr=$tail"
        }
    }
}

Set-BalancedPlan
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    $outputs = @($run1, $run2)
    for ($index = 0; $index -lt 2; $index += 1) {
        $runNumber = $index + 1
        $script:runPassed = $false
        Invoke-Run $runNumber $outputs[$index]
        if (-not $script:runPassed) {
            & $python $failFastScript --config $config --partial-run $outputs[$index] `
                --run-number $runNumber --output $gate
            if ($LASTEXITCODE -ne 0) { throw 'Fail-fast gate writer failed' }
            Write-Output "STAGE1_FAIL_FAST run=$runNumber gate=$gate"
            return
        }
        Unload-Model
        Set-BalancedPlan
        Write-Output "RUN_COMPLETE run=$runNumber records=$expected"
    }
    & $python $auditScript --config $config --left $run1 --right $run2 --output $gate
    if ($LASTEXITCODE -ne 0) { throw 'Stage 1 audit/gate failed' }
    Write-Output "STAGE1_COMPLETE gate=$gate"
}
finally {
    Stop-Producer
    Unload-Model
    try { Set-BalancedPlan }
    catch { Write-Output "BALANCED_RESTORE_WARNING=$($_.Exception.Message)" }
    Remove-EmptyRedirectLogs -Directory $logs
    $temperature = Get-GpuTemperatureC
    Write-Output "SAFETY_CLEANUP_COMPLETE power_plan=Balanced gpu_temp_c=$temperature"
}


