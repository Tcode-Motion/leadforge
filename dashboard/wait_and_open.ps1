param(
    [Parameter(Mandatory=$true)][string]$InfoPath,
    [Parameter(Mandatory=$true)][string]$LaunchToken,
    [string]$LogPath = "",
    [int]$TimeoutSeconds = 40
)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    try {
        if (Test-Path -LiteralPath $InfoPath) {
            $info = Get-Content -LiteralPath $InfoPath -Raw | ConvertFrom-Json
            if ($info.url -and $info.launch_token) {
                try {
                    $health = Invoke-RestMethod -Uri ($info.url + "/api/health") -TimeoutSec 2
                    if ($health.app -eq "LeadForge" -and $health.server.token -eq $info.launch_token) {
                        Start-Process $info.url
                        exit 0
                    }
                } catch {
                    # The server may still be starting. Keep waiting.
                }
            }
        }
    } catch {
        # A half written or stale info file should not stop the wait.
    }
    Start-Sleep -Milliseconds 500
}

Write-Host "LeadForge did not answer in time."
if ($LogPath) {
    Write-Host "Read the log here:"
    Write-Host $LogPath
}
exit 1
