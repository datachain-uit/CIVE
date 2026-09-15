param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Script,
    [Parameter(Mandatory=$true)][string]$InputArtifact,
    [Parameter(Mandatory=$true)][string]$OutputArtifact,
    [Parameter(Mandatory=$true)][string]$CacheDir,
    [Parameter(Mandatory=$true)][string]$PySitePackages,
    [Parameter(Mandatory=$true)][string]$Revision,
    [int]$MaxGpuTempC = 75
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'thermal_safe_log_helpers.ps1')
$balancedGuid = '381b4222-f694-41f0-9685-ff5bb260df2e'

function Get-GpuState {
    $raw = & nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader,nounits
    $parts = $raw -split ','
    [pscustomobject]@{
        TemperatureC = [int]($parts[0].Trim())
        UtilizationPct = [int]($parts[1].Trim())
        MemoryMiB = [int]($parts[2].Trim())
    }
}

$startGpu = Get-GpuState
if ($startGpu.TemperatureC -ge $MaxGpuTempC) {
    throw "GPU temperature $($startGpu.TemperatureC)C is at or above hard limit ${MaxGpuTempC}C; refusing to start."
}

try {
    & powercfg /SETACTIVE $balancedGuid | Out-Null
} catch {
    Write-Host "WARN: could not switch to Windows Balanced power plan: $($_.Exception.Message)"
}

$runId = [guid]::NewGuid().ToString('N')
$logDir = Join-Path $env:TEMP "cryptobert_full_$runId"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stdout = Join-Path $logDir 'stdout.log'
$stderr = Join-Path $logDir 'stderr.log'
$thermal = Join-Path $logDir 'thermal.csv'
"timestamp_utc,temperature_c,utilization_pct,memory_mib" | Set-Content -Path $thermal -Encoding UTF8

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Python
$psi.ArgumentList.Add($Script)
$psi.ArgumentList.Add('--stage')
$psi.ArgumentList.Add('full')
$psi.ArgumentList.Add('--input')
$psi.ArgumentList.Add($InputArtifact)
$psi.ArgumentList.Add('--output')
$psi.ArgumentList.Add($OutputArtifact)
$psi.ArgumentList.Add('--cache-dir')
$psi.ArgumentList.Add($CacheDir)
$psi.ArgumentList.Add('--revision')
$psi.ArgumentList.Add($Revision)
$psi.ArgumentList.Add('--local-files-only')
$psi.ArgumentList.Add('--resume')
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.Environment['PYTHONPATH'] = $PySitePackages
$psi.Environment['PYTHONIOENCODING'] = 'utf-8'

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
$null = $process.Start()

$outTask = $process.StandardOutput.ReadToEndAsync()
$errTask = $process.StandardError.ReadToEndAsync()
$killedForThermal = $false

while (-not $process.HasExited) {
    Start-Sleep -Seconds 5
    $gpu = Get-GpuState
    $line = "$(Get-Date -AsUTC -Format o),$($gpu.TemperatureC),$($gpu.UtilizationPct),$($gpu.MemoryMiB)"
    Add-Content -Path $thermal -Value $line -Encoding UTF8
    if ($gpu.TemperatureC -ge $MaxGpuTempC) {
        $killedForThermal = $true
        Stop-Process -Id $process.Id -Force
        break
    }
}

$process.WaitForExit()
$outTask.Result | Set-Content -Path $stdout -Encoding UTF8
$errTask.Result | Set-Content -Path $stderr -Encoding UTF8

$endGpu = Get-GpuState
try {
    & powercfg /SETACTIVE $balancedGuid | Out-Null
} catch {
    Write-Host "WARN: could not restore Windows Balanced power plan: $($_.Exception.Message)"
}

Write-Host "LOG_DIR=$logDir"
Write-Host "START_GPU=$($startGpu.TemperatureC),$($startGpu.UtilizationPct),$($startGpu.MemoryMiB)"
Write-Host "END_GPU=$($endGpu.TemperatureC),$($endGpu.UtilizationPct),$($endGpu.MemoryMiB)"
Write-Host "EXIT_CODE=$($process.ExitCode)"
Write-Host "KILLED_FOR_THERMAL=$killedForThermal"
Write-Host "STDOUT_TAIL:"
Get-Content -Path $stdout -Tail 20
Write-Host "STDERR_TAIL:"
Get-Content -Path $stderr -Tail 20
Remove-EmptyRedirectLogs -Directory $logDir

if ($killedForThermal) {
    exit 75
}
exit $process.ExitCode
