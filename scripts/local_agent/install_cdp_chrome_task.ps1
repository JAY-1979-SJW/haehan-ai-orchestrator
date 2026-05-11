# Haehan AI Orchestrator — CDP Chrome Task Scheduler 등록
# 1회 실행으로 'HaehanCdpChrome' Task 등록.

param(
    [string]$ChromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe",
    [int]$Port = 9222,
    [string]$ProfileDir = "C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\data\cdp_profile",
    [string]$TaskName = "HaehanCdpChrome"
)

if (-not (Test-Path $ChromePath)) {
    Write-Error "Chrome 미발견: $ChromePath"
    exit 1
}

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

# 시작 URL 포함 — 사용자 수동 입력 불필요. about:blank 대신 가시 페이지 표시
$StartUrl = "https://www.naver.com"
$argLine = "--remote-debugging-port=$Port --user-data-dir=`"$ProfileDir`" --no-first-run --no-default-browser-check --new-window $StartUrl"

$action  = New-ScheduledTaskAction -Execute $ChromePath -Argument $argLine
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Haehan AI Orchestrator: Chrome with CDP port $Port"

Write-Host "[OK] Task '$TaskName' 등록 완료"
Write-Host "    실행: schtasks /run /tn $TaskName"
Write-Host "    제거: schtasks /delete /tn $TaskName /f"
