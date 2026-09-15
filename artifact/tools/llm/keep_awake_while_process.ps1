param(
    [Parameter(Mandatory = $true)]
    [int]$TargetProcessId
)

$ErrorActionPreference = 'Stop'
$source = @'
using System;
using System.Runtime.InteropServices;
public static class ExecutionState {
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@
Add-Type -TypeDefinition $source

$continuous = [Convert]::ToUInt32('80000000', 16)
$systemRequired = [uint32]0x00000001
try {
    while (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) {
        $result = [ExecutionState]::SetThreadExecutionState($continuous -bor $systemRequired)
        if ($result -eq 0) { throw 'SetThreadExecutionState failed' }
        Start-Sleep -Seconds 30
    }
}
finally {
    [void][ExecutionState]::SetThreadExecutionState($continuous)
}
