param([int]$RequestDelaySeconds = 2)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = 'C:\Users\MN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$config = Join-Path $workspace 'paper\input\results\llm\v11\open_fed_policy_extraction_v11_1_predeclared.json'
$output = Join-Path $workspace 'paper\input\results\llm\v11\open_fed_policy_extraction_v11_1.json'
$scriptFile = Join-Path $workspace 'tools\llm\score_open_fed_policy_v11_1.py'
$model='ministral-3:8b'; $expected=110; $hardCeilingC=75; $resumeAtC=70; $pollSeconds=5; $producer=$null
function Test-Balanced { (powercfg /getactivescheme) -match '381b4222-f694-41f0-9685-ff5bb260df2e' }
function Set-Balanced { if (-not (Test-Balanced)) { powercfg /setactive SCHEME_BALANCED | Out-Null }; if (-not (Test-Balanced)) { throw 'Cannot activate Balanced' } }
function Get-Temp { $raw=& nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits; $value=0; if ($LASTEXITCODE -ne 0 -or @($raw).Count -ne 1 -or -not [int]::TryParse(([string]$raw).Trim(),[ref]$value)) { throw 'Cannot read exactly one NVIDIA GPU temperature; failing closed' }; $value }
function Stop-Producer { if ($null -ne $script:producer) { $script:producer.Refresh(); if (-not $script:producer.HasExited) { Stop-Process -Id $script:producer.Id -Force; $script:producer.WaitForExit(10000) | Out-Null }; $script:producer=$null } }
function Unload { try { & 'C:\Users\MN\AppData\Local\Programs\Ollama\ollama.exe' stop $model | Out-Null } catch { Write-Output "UNLOAD_WARNING=$($_.Exception.Message)" } }
function State { if (-not (Test-Path $output)) { return [pscustomobject]@{attempted=0;success=0;errors=0} }; (Get-Content $output -Raw | ConvertFrom-Json).summary }
function Wait-Cool { while ((Get-Temp) -gt $resumeAtC) { Unload; Start-Sleep -Seconds $pollSeconds } }
Set-Balanced
try {
  while ($true) {
    $state=State; if ($state.errors -gt 0) { throw "Fail-fast extraction error after $($state.attempted) events" }; if ($state.success -eq $expected) { break }
    Wait-Cool; Set-Balanced
    $args=@($scriptFile,'--config',$config,'--output',$output,'--request-delay-seconds',"$RequestDelaySeconds")
    $script:producer=Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $workspace -WindowStyle Hidden -PassThru
    Write-Output "V11_1_START pid=$($script:producer.Id) completed=$($state.success)"; $thermalTrip=$false
    while (-not $script:producer.HasExited) {
      Start-Sleep -Seconds $pollSeconds; $script:producer.Refresh(); $temperature=Get-Temp; $state=State
      Write-Output "V11_1_THERMAL temp_c=$temperature completed=$($state.success) errors=$($state.errors)"
      if (-not (Test-Balanced)) { Write-Output 'POWER_PLAN_RESTORE'; Set-Balanced; Write-Output 'POWER_PLAN_RESTORED' }
      if ($state.errors -gt 0) { Stop-Producer; Unload; throw "Fail-fast extraction error after $($state.attempted) events" }
      if ($temperature -ge $hardCeilingC) { Stop-Producer; Unload; Set-Balanced; $thermalTrip=$true; break }
    }
    if ($thermalTrip) { continue }
    $script:producer.WaitForExit(); $exit=$script:producer.ExitCode; $script:producer=$null; if ($exit -ne 0) { throw "Producer exited $exit" }
  }
  Write-Output "V11_1_EXTRACTION_COMPLETE output=$output"
}
finally {
  Stop-Producer; Unload; Set-Balanced; Start-Sleep -Seconds 2
  $temperature=Get-Temp; $util=& nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits
  Write-Output "SAFETY_CLEANUP_COMPLETE power_plan=Balanced gpu_temp_c=$temperature gpu_util_pct=$(([string]$util).Trim())"
}
