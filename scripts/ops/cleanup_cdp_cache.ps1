# CDP 브라우저 캐시 정리 스크립트
# 보존: Cookies, Login Data, Network/Cookies (로그인 세션)
# 삭제: 그 외 전부

$CDP_PROFILE = "C:\work\01. haehan-ai-orchestrator\data\cdp_profile\ai_chrome"
$DEFAULT = "$CDP_PROFILE\Default"

if (-not (Test-Path $CDP_PROFILE)) {
    Write-Host "[cdp-cleanup] 프로필 없음 — 생략"
    exit 0
}

# Chrome 실행 중이면 정리 생략 (파일 잠김 방지)
$chrome = Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Where-Object {
    (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)" -EA SilentlyContinue).CommandLine -like "*ai_chrome*"
}
if ($chrome) {
    Write-Host "[cdp-cleanup] Chrome 실행 중 — 정리 생략"
    exit 0
}

$before = (Get-ChildItem $CDP_PROFILE -Recurse -File -EA SilentlyContinue | Measure-Object Length -Sum).Sum

# 보존 목록 (로그인 관련)
$keep = @(
    "$DEFAULT\Cookies",
    "$DEFAULT\Cookies-journal",
    "$DEFAULT\Login Data",
    "$DEFAULT\Login Data-journal",
    "$DEFAULT\Login Data For Account",
    "$DEFAULT\Login Data For Account-journal",
    "$DEFAULT\Network\Cookies",
    "$DEFAULT\Network\Cookies-journal",
    "$DEFAULT\Secure Preferences",
    "$DEFAULT\Preferences"
)

# Default 내 항목 삭제 (보존 목록 제외)
if (Test-Path $DEFAULT) {
    Get-ChildItem $DEFAULT | ForEach-Object {
        $fullPath = $_.FullName
        $isKeep = $keep | Where-Object { $_ -eq $fullPath }
        if (-not $isKeep) {
            Remove-Item $fullPath -Recurse -Force -EA SilentlyContinue
        }
    }
}

# Default 외 루트 항목 전부 삭제 (GrShaderCache 등)
Get-ChildItem $CDP_PROFILE | Where-Object { $_.Name -ne "Default" } | ForEach-Object {
    Remove-Item $_.FullName -Recurse -Force -EA SilentlyContinue
}

$after = (Get-ChildItem $CDP_PROFILE -Recurse -File -EA SilentlyContinue | Measure-Object Length -Sum).Sum
$freed = [math]::Round(($before - $after) / 1MB, 1)
$remain = [math]::Round($after / 1MB, 1)

Write-Host "[cdp-cleanup] 완료 — 해제: ${freed}MB / 잔여: ${remain}MB"
