$ErrorActionPreference = "Stop"

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class ExecutionState {
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

$continuous = [Convert]::ToUInt32("80000000", 16)
$systemRequired = [uint32]0x00000001

try {
    $result = [ExecutionState]::SetThreadExecutionState($continuous -bor $systemRequired)
    if ($result -eq 0) {
        throw "SetThreadExecutionState failed."
    }
    while ($true) {
        Start-Sleep -Seconds 30
    }
}
finally {
    [void][ExecutionState]::SetThreadExecutionState($continuous)
}
