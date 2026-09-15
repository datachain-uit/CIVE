param(
    [string]$RunRoot = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'runtime\ministral3_8b_challenger'),
    [string]$ConfigFile = 'llm_event_extractor_v3_3_full_predeclared.json',
    [string]$OutputTag = 'v3_3',
    [string]$ProducerFile = 'score_llm_event_extractor_v3_full.py',
    [string]$AuditFile = 'evaluate_llm_event_extractor_v3_full.py',
    [int]$RequestDelaySeconds = 10
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$config = Join-Path (Join-Path $RunRoot 'configs') $ConfigFile
$inputArtifact = Join-Path $workspace 'paper\input\results\llm\v3\llm_event_extraction_inputs_v3_development.json'
$producerScript = Join-Path (Join-Path $workspace 'tools\llm') $ProducerFile
$auditScript = Join-Path (Join-Path $workspace 'tools\llm') $AuditFile
$results = Join-Path $RunRoot 'results'
$logs = Join-Path $RunRoot 'logs'
$checkpoint = Join-Path $results "llm_event_extractor_${OutputTag}_full_checkpoint.ndjson"
$progress = Join-Path $results "llm_event_extractor_${OutputTag}_full_progress.json"
$output = Join-Path $results "llm_event_extractor_${OutputTag}_full_development.json"
$gate = Join-Path $results "llm_event_extractor_${OutputTag}_full_gate.json"
$model = 'ministral-3:8b'
$expected = 39393
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 5
$session = Get-Date -Format 'yyyyMMdd_HHmmss'
$producer = $null

foreach ($path in @($workspace, $RunRoot, $python, $config, $inputArtifact, $producerScript, $auditScript)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}
New-Item -ItemType Directory -Force -Path $results, $logs | Out-Null

function Test-BalancedPlan {
    $active = powercfg /getactivescheme
    return $LASTEXITCODE -eq 0 -and $active -match '381b4222-f694-41f0-9685-ff5bb260df2e'
}

function Set-BalancedPlan {
    if (Test-BalancedPlan) { return }
    powercfg /setactive SCHEME_BALANCED | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-BalancedPlan)) { throw 'Failed to activate Windows Balanced' }
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

function Get-State {
    if (-not (Test-Path -LiteralPath $progress)) {
        return [pscustomobject]@{ Records = 0; Success = 0; Errors = 0 }
    }
    $payload = Get-Content -LiteralPath $progress -Raw | ConvertFrom-Json
    return [pscustomobject]@{
        Records = [int]$payload.records
        Success = [int]$payload.success
        Errors = [int]$payload.errors
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

function Wait-UntilCool {
    $temperature = Get-GpuTemperatureC
    while ($temperature -gt $resumeAtC) {
        Write-Output "COOLDOWN gpu_temp_c=$temperature time=$(Get-Date -Format o)"
        Start-Sleep -Seconds $pollSeconds
        $temperature = Get-GpuTemperatureC
    }
}

Set-BalancedPlan
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    while ($true) {
        $state = Get-State
        if ($state.Errors -gt 0) {
            Write-Output "FULL_EXTRACTION_FAIL_FAST records=$($state.Records) errors=$($state.Errors)"
            return
        }
        if ($state.Records -eq $expected -and $state.Success -eq $expected -and
            (Test-Path -LiteralPath $output)) { break }
        if ($state.Records -gt $expected) { throw 'Checkpoint exceeds expected full-input records' }

        Wait-UntilCool
        Set-BalancedPlan
        Remove-EmptyRedirectLogs -Directory $logs
        $stdout = Join-Path $logs "event_${OutputTag}_full_${session}.stdout.log"
        $stderr = Join-Path $logs "event_${OutputTag}_full_${session}.stderr.log"
        $arguments = @(
            $producerScript, '--config', $config, '--input', $inputArtifact,
            '--checkpoint', $checkpoint, '--progress', $progress, '--output', $output,
            '--run-id', "event-$OutputTag-full-extraction",
            '--request-delay-seconds', "$RequestDelaySeconds"
        )
        $script:producer = Start-Process -FilePath $python -ArgumentList $arguments `
            -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        Write-Output "FULL_EXTRACTION_START pid=$($script:producer.Id) records=$($state.Records)"
        $thermalTrip = $false
        while (-not $script:producer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $script:producer.Refresh()
            $temperature = Get-GpuTemperatureC
            $state = Get-State
            Write-Output "THERMAL gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
            if (-not (Test-BalancedPlan)) {
                Write-Output "POWER_PLAN_RESTORE records=$($state.Records)"
                try {
                    Set-BalancedPlan
                    Write-Output "POWER_PLAN_RESTORED records=$($state.Records)"
                }
                catch {
                    Write-Output "POWER_PLAN_STOP records=$($state.Records)"
                    Stop-Producer
                    Unload-Model
                    throw 'Active power plan changed away from Balanced and could not be restored'
                }
            }
            if ($state.Errors -gt 0) {
                Stop-Producer
                Unload-Model
                Write-Output "FULL_EXTRACTION_FAIL_FAST records=$($state.Records) errors=$($state.Errors)"
                return
            }
            if ($temperature -ge $hardCeilingC) {
                Write-Output "THERMAL_STOP gpu_temp_c=$temperature records=$($state.Records)"
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
        $finalState = Get-State
        if ($exitCode -ne 0 -and -not ($finalState.Records -eq $expected -and $finalState.Success -eq $expected -and $finalState.Errors -eq 0)) {
            $tail = if (Test-Path $stderr) { Get-Content $stderr -Tail 30 | Out-String } else { '' }
            throw "Full extraction producer failed exit=$exitCode stderr=$tail"
        }
    }

    & $python $auditScript --config $config --input $inputArtifact --extraction $output --output $gate
    if ($LASTEXITCODE -ne 0) { throw 'Full extraction completion audit failed' }
    Write-Output "FULL_EXTRACTION_COMPLETE gate=$gate"
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

