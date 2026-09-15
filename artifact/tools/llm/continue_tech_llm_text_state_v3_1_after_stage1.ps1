param([int]$RequestDelaySeconds = 10, [int]$Stage1TimeoutMinutes = 180)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = if ($env:KLTN_PYTHON_EXE) { $env:KLTN_PYTHON_EXE } else { (Get-Command python -ErrorAction Stop).Source }
$runRoot = Join-Path $workspace 'runtime\ministral3_8b_challenger'
$stage1Config = Join-Path $runRoot 'configs\tech_llm_text_state_extractor_v3_1_stage1_predeclared.json'
$stage1Gate = Join-Path $runRoot 'results\tech_llm_text_state_v3_1_stage1_gate.json'
$stage1Run1 = Join-Path $runRoot 'results\tech_llm_text_state_v3_1_stage1_run1.json'
$stage1Run2 = Join-Path $runRoot 'results\tech_llm_text_state_v3_1_stage1_run2.json'
$fullConfig = Join-Path $runRoot 'configs\tech_llm_text_state_extractor_v3_1_full_predeclared.json'
$predeclare = Join-Path $workspace 'tools\llm\predeclare_tech_llm_text_state_full_v3_1.py'
$fullAudit = Join-Path $workspace 'tools\llm\evaluate_tech_llm_text_state_full_v3.py'
$fullRunner = Join-Path $workspace 'tools\llm\run_tech_llm_text_state_full_v3_1_thermal_safe.ps1'
$canonicalStage1 = Join-Path $workspace 'paper\input\results\hybrid\hyb003_text_state_stage1_v3_1'

foreach ($path in @($python, $stage1Config, $predeclare, $fullAudit, $fullRunner)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path missing: $path" }
}

$deadline = (Get-Date).AddMinutes($Stage1TimeoutMinutes)
while (-not (Test-Path -LiteralPath $stage1Gate)) {
    if ((Get-Date) -ge $deadline) { throw 'Timed out waiting for the v3.1 Stage-1 gate' }
    Start-Sleep -Seconds 30
}
$gate = Get-Content -LiteralPath $stage1Gate -Raw | ConvertFrom-Json
if (-not $gate.passed -or $gate.status -ne 'stage1-pass-full-text-state-extraction-authorized') {
    throw "v3.1 Stage-1 gate did not pass: $($gate.status)"
}

New-Item -ItemType Directory -Force -Path $canonicalStage1 | Out-Null
Copy-Item -LiteralPath $stage1Config -Destination (Join-Path $canonicalStage1 'predeclared.json') -Force
Copy-Item -LiteralPath $stage1Run1 -Destination (Join-Path $canonicalStage1 'run1.json') -Force
Copy-Item -LiteralPath $stage1Run2 -Destination (Join-Path $canonicalStage1 'run2.json') -Force
Copy-Item -LiteralPath $stage1Gate -Destination (Join-Path $canonicalStage1 'gate.json') -Force

& $python $predeclare --stage1-config $stage1Config --stage1-gate $stage1Gate --audit $fullAudit --output $fullConfig
if ($LASTEXITCODE -ne 0) { throw 'Failed to freeze v3.1 full-extraction predeclaration' }
Write-Output "V3_1_FULL_PREDECLARED config=$fullConfig"

& 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -ExecutionPolicy Bypass -File $fullRunner -RequestDelaySeconds $RequestDelaySeconds
if ($LASTEXITCODE -ne 0) { throw "v3.1 full runner failed with exit code $LASTEXITCODE" }
