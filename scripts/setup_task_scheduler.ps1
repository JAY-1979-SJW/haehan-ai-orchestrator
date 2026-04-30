# setup_task_scheduler.ps1 (DESK-3)
#
# Windows Task Scheduler 등록: 사용자 로그온 시 haehan agent tray app 자동 시작
#
# 사용법:
#   .\scripts\setup_task_scheduler.ps1
#   .\scripts\setup_task_scheduler.ps1 -Uninstall
#   .\scripts\setup_task_scheduler.ps1 -PythonPath "C:\path\to\python.exe"
#
# 보안:
#   - 인증 관련 값 미포함 (see: local_agent/redaction.py for redaction policy)
#   - 운영 서버 URL 없음
#   - 로컬 자동시작 전용

param(
    [switch]$Uninstall,
    [string]$PythonPath = "",
    [string]$RepoRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName = "HaehanAgentTray"
$TaskDescription = "Haehan AI Orchestrator - local agent tray app autostart at logon"

# Resolve paths
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$TrayScript = Join-Path $RepoRoot "desktop\tray_app.py"

if (-not $PythonPath) {
    try {
        $PythonPath = (Get-Command python -ErrorAction Stop).Source
    }
    catch {
        Write-Error "python not found in PATH. Use -PythonPath to specify."
        exit 1
    }
}

# ── Uninstall ──────────────────────────────────────────────────────────────

if ($Uninstall) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] Task '$TaskName' removed."
    }
    else {
        Write-Host "[INFO] Task '$TaskName' not found. Nothing to remove."
    }
    exit 0
}

# ── Install ────────────────────────────────────────────────────────────────

Write-Host "[INFO] Registering Task Scheduler task: $TaskName"
Write-Host "[INFO] Python:     $PythonPath"
Write-Host "[INFO] Script:     $TrayScript"
Write-Host "[INFO] Trigger:    AtLogon (current user)"

# Validate script exists
if (-not (Test-Path $TrayScript)) {
    Write-Error "Tray script not found: $TrayScript"
    exit 1
}

# Action: run python desktop/tray_app.py
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$TrayScript`"" `
    -WorkingDirectory $RepoRoot

# Trigger: at user logon
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Settings: start when available, restart on failure (3 times, 1 min interval)
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

# Principal: run as current user, limited rights (no elevation)
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

# Register
Register-ScheduledTask `
    -TaskName $TaskName `
    -Description $TaskDescription `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
Write-Host "[OK] Task registered: $($task.TaskName)"
Write-Host "[OK] State:           $($task.State)"
Write-Host ""
Write-Host "To verify:  schtasks /query /tn `"$TaskName`" /fo LIST /v"
Write-Host "To remove:  .\scripts\setup_task_scheduler.ps1 -Uninstall"
