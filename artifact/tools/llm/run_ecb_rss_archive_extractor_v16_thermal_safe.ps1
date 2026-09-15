param([int]$RequestDelaySeconds = 5)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$runner = Join-Path $PSScriptRoot 'resume_ecb_rss_archive_extractor_v16.py'
$output = Join-Path $workspace 'paper\input\results\llm\v16\ecb_rss_archive_predictive_v16\extraction'
$logs = Join-Path $workspace 'runtime\ministral3_8b_challenger\logs'
$model = 'ministral-3:8b'
$producer = $null

function Set-Balanced {
    powercfg /setactive SCHEME_BALANCED | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to activate Windows Balanced power plan' }
}
function Temp {
    $raw = & nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits
    $value = 0
    if ($LASTEXITCODE -ne 0 -or @($raw).Count -ne 1 -or -not [int]::TryParse(([string]$raw).Trim(), [ref]$value)) { throw 'Cannot read one GPU temperature; failing closed' }
    return $value
}
function Stop-Producer {
    if ($null -ne $script:producer) {
        $script:producer.Refresh()
        if (-not $script:producer.HasExited) { Stop-Process -Id $script:producer.Id -Force }
        $script:producer = $null
    }
}
function Unload {
    try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/generate' -Method Post -ContentType 'application/json' -Body (@{model=$model;prompt='';stream=$false;keep_alive=0}|ConvertTo-Json) -TimeoutSec 30 | Out-Null } catch { Write-Output "OLLAMA_UNLOAD_WARNING=$($_.Exception.Message)" }
}

foreach ($path in @($python, $runner)) { if (-not (Test-Path -LiteralPath $path)) { throw "Missing required path: $path" } }
New-Item -ItemType Directory -Force -Path $output, $logs | Out-Null
Set-Balanced
try {
    while ($true) {
        $progress = Join-Path $output 'extraction_progress.json'
        if (Test-Path $progress) {
            $state = Get-Content -LiteralPath $progress -Raw | ConvertFrom-Json
            if ($state.errors -gt 0) { throw "EXTRACTION_FAIL_FAST records=$($state.records) errors=$($state.errors)" }
            if ($state.records -eq $state.expected_records) { break }
        }
        while ((Temp) -gt 70) { Write-Output "COOLDOWN gpu_temp_c=$(Temp)"; Start-Sleep -Seconds 5 }
        $stdout = Join-Path $logs 'ecb_rss_v16.stdout.log'
        $stderr = Join-Path $logs 'ecb_rss_v16.stderr.log'
        $script:producer = Start-Process -FilePath $python -ArgumentList @($runner, '--output-dir', $output, '--request-delay-seconds', "$RequestDelaySeconds") -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        while (-not $script:producer.HasExited) {
            Start-Sleep -Seconds 5
            $script:producer.Refresh()
            $temperature = Temp
            $state = if (Test-Path $progress) { Get-Content -LiteralPath $progress -Raw | ConvertFrom-Json } else { $null }
            Write-Output "THERMAL gpu_temp_c=$temperature records=$($state.records) errors=$($state.errors)"
            if ($temperature -ge 75) { Write-Output "THERMAL_STOP gpu_temp_c=$temperature"; Stop-Producer; Unload; Set-Balanced; break }
            if ($null -ne $state -and $state.errors -gt 0) { Stop-Producer; Unload; throw "EXTRACTION_FAIL_FAST records=$($state.records) errors=$($state.errors)" }
        }
        if ($null -ne $script:producer) { $script:producer.WaitForExit(); $exit = $script:producer.ExitCode; $script:producer = $null; if ($exit -ne 0) { throw "Extraction runner failed exit=$exit" } }
    }
    Write-Output 'EXTRACTION_COMPLETE'
}
finally { Stop-Producer; Unload; Set-Balanced; Write-Output "SAFETY_CLEANUP_COMPLETE gpu_temp_c=$(Temp)" }

