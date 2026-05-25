# setup_task_scheduler.ps1
#
# Legacy cleanup helper.
#
# The desktop/local-agent runtime must be user-started or task-scoped. This
# script intentionally does not register logon autostart jobs. It only removes
# legacy Haehan Task Scheduler entries that could relaunch an old local app.
#
# Usage:
#   .\scripts\setup_task_scheduler.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskNames = @(
    "HaehanAgentTray",
    "HaehanAgentWatchdog",
    "HaehanCdpDaemon",
    "HaehanCdpChrome"
)

foreach ($TaskName in $TaskNames) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] Removed legacy task: $TaskName"
    }
    else {
        Write-Host "[INFO] Legacy task not found: $TaskName"
    }
}

Write-Host "[OK] Legacy Haehan autostart cleanup complete."
