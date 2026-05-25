# Legacy cleanup helper for the old HaehanCdpChrome Task Scheduler job.
#
# This script intentionally does not register a logon task. CDP Chrome must be
# started explicitly by an approved task-scoped runtime path.

param(
    [string]$TaskName = "HaehanCdpChrome"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "[OK] Removed legacy task: $TaskName"
}
else {
    Write-Host "[INFO] Legacy task not found: $TaskName"
}
