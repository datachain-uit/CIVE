param([int]$RequestDelaySeconds = 10)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')

$workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$runRoot = Join-Path $workspace 'runtime\ministral3_8b_challenger'
$config = Join-Path $runRoot 'configs\tech_llm_text_state_extractor_v3_1_stage1_predeclared.json'
$inputArtifact = Join-Path $workspace 'paper\input\results\hybrid\tech_llm_text_state_reliability_sample_v3_frozen.json'
$scorer = Join-Path $workspace 'tools\llm\score_tech_llm_text_state_v3_1.py'
$auditor = Join-Path $workspace 'tools\llm\evaluate_tech_llm_text_state_stage1_v3.py'
$results = Join-Path $runRoot 'results'
$logs = Join-Path $runRoot 'logs'
$run1 = Join-Path $results 'tech_llm_text_state_v3_1_stage1_run1.json'
$run2 = Join-Path $results 'tech_llm_text_state_v3_1_stage1_run2.json'
$gate = Join-Path $results 'tech_llm_text_state_v3_1_stage1_gate.json'
$model = 'ministral-3:8b'
$expected = 96
$hardCeilingC = 75
$resumeAtC = 70
$pollSeconds = 5
$producer = $null
$session = Get-Date -Format 'yyyyMMdd_HHmmss'

foreach ($path in @($workspace, $python, $config, $inputArtifact, $scorer, $auditor)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path missing: $path" }
}
New-Item -ItemType Directory -Force -Path $results, $logs | Out-Null

function Set-BalancedPlan {
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
    if ($LASTEXITCODE -ne 0 -or @($raw).Count -ne 1 -or -not [int]::TryParse(([string]$raw).Trim(), [ref]$value)) {
        throw 'Cannot read exactly one NVIDIA GPU temperature; failing closed'
    }
    return $value
}

function Get-State([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return [pscustomobject]@{Records=0; Success=0; Errors=0} }
    $payload = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    return [pscustomobject]@{
        Records=@($payload.records).Count
        Success=[int]$payload.summary.success
        Errors=[int]$payload.summary.errors
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
        $body = @{model=$model; prompt=''; stream=$false; keep_alive=0} | ConvertTo-Json
        Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/generate' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 30 | Out-Null
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
        if ($state.Errors -gt 0) { throw "Stage 1 fail-fast: run $RunNumber has schema errors" }
        if ($state.Records -eq $expected -and $state.Success -eq $expected) { return }
        if ($state.Records -gt $expected) { throw "Run $RunNumber exceeds expected record count" }
        Wait-UntilCool $RunNumber
        Set-BalancedPlan
        Remove-EmptyRedirectLogs -Directory $logs
        $cycle += 1
        $stdout = Join-Path $logs "hyb003_text_${session}_run${RunNumber}_cycle${cycle}.stdout.log"
        $stderr = Join-Path $logs "hyb003_text_${session}_run${RunNumber}_cycle${cycle}.stderr.log"
        $arguments = @(
            $scorer, '--config', $config, '--input', $inputArtifact, '--output', $Output,
            '--run-id', "hyb003-text-v3.1-stage1-run$RunNumber", '--request-delay-seconds', "$RequestDelaySeconds"
        )
        $script:producer = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        Write-Output "SCORING_START run=$RunNumber cycle=$cycle pid=$($script:producer.Id) records=$($state.Records)"
        $thermalTrip = $false
        while (-not $script:producer.HasExited) {
            Start-Sleep -Seconds $pollSeconds
            $script:producer.Refresh()
            $temperature = Get-GpuTemperatureC
            $state = Get-State $Output
            Write-Output "THERMAL run=$RunNumber cycle=$cycle gpu_temp_c=$temperature records=$($state.Records) errors=$($state.Errors)"
            if (-not (Test-BalancedPlan)) { Set-BalancedPlan }
            if ($state.Errors -gt 0) {
                Stop-Producer
                Unload-Model
                throw "Stage 1 fail-fast: run $RunNumber produced an error"
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
        $final = Get-State $Output
        if ($exitCode -ne 0 -and -not ($final.Records -eq $expected -and $final.Success -eq $expected -and $final.Errors -eq 0)) {
            $tail = if (Test-Path $stderr) { Get-Content -LiteralPath $stderr -Tail 20 | Out-String } else { '' }
            throw "Scorer failed exit=$exitCode stderr=$tail"
        }
    }
}

Set-BalancedPlan
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    Invoke-Run 1 $run1
    Unload-Model
    Set-BalancedPlan
    Write-Output 'RUN_COMPLETE run=1 records=96'
    Invoke-Run 2 $run2
    Unload-Model
    Set-BalancedPlan
    Write-Output 'RUN_COMPLETE run=2 records=96'
    & $python $auditor --config $config --left $run1 --right $run2 --output $gate
    if ($LASTEXITCODE -ne 0) { throw 'Reliability auditor failed' }
    Write-Output "STAGE1_COMPLETE gate=$gate"
}
finally {
    Stop-Producer
    Unload-Model
    try { Set-BalancedPlan } catch { Write-Output "BALANCED_RESTORE_WARNING=$($_.Exception.Message)" }
    Remove-EmptyRedirectLogs -Directory $logs
    $temperature = Get-GpuTemperatureC
    $utilization = & nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits
    Write-Output "SAFETY_CLEANUP_COMPLETE power_plan=Balanced gpu_temp_c=$temperature gpu_util_pct=$(([string]$utilization).Trim())"
}
