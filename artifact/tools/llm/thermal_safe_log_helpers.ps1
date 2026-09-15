function Remove-EmptyRedirectLogs {
    param([Parameter(Mandatory = $true)][string]$Directory)

    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return }

    foreach ($log in Get-ChildItem -LiteralPath $Directory -File -ErrorAction Stop) {
        $isRedirectLog = $log.Name.EndsWith('.stdout.log') -or $log.Name.EndsWith('.stderr.log')
        if ($isRedirectLog -and $log.Length -eq 0) {
            try {
                [System.IO.File]::Delete($log.FullName)
            }
            catch {
                Write-Warning "Could not remove empty redirect log '$($log.FullName)': $($_.Exception.Message)"
            }
        }
    }
}
