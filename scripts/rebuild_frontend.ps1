# Haehan AI 프론트(Next.js) 재빌드 자동화
# next build 의 함정(파일락 행·static 미복사·standalone env 초기화)을 한 번에 처리.
# 사용: powershell -ExecutionPolicy Bypass -File scripts\rebuild_frontend.ps1
#
# 왜 필요한가:
#  1) 실행 중인 :3000 서버가 .next/ 를 잠가 next build 가 무한 행 → 먼저 종료.
#  2) standalone 은 .next/static·public 을 자동복사 안 함 → 수동 복사(누락 시 흰화면).
#  3) 빌드가 standalone 에 remote .env.production 만 복사 → 로컬 URL·API_PASS 재보정
#     (안 하면 AI 상담 401·원격行). 자세한 배경: 메모리 desktop-backend-target.

$ErrorActionPreference = "Stop"
$ROOT = "C:\work\01. haehan-ai-orchestrator"
$WEB  = "$ROOT\admin-web"
$STD  = "$WEB\.next\standalone"
$node = (Get-Command node).Source

function Write-EnvNoBom($path, $lines) {
    [System.IO.File]::WriteAllLines($path, $lines, (New-Object System.Text.UTF8Encoding $false))
}

Write-Host "[1/5] Next 서버(:3000) 종료 — .next 파일락 해제..." -ForegroundColor Cyan
Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3

Write-Host "[2/5] next build (telemetry off)..." -ForegroundColor Cyan
$env:NEXT_TELEMETRY_DISABLED = "1"; $env:NODE_ENV = "production"
Push-Location $WEB
try { & $node "$WEB\node_modules\next\dist\bin\next" build | Out-Host }
finally { Pop-Location }
if (-not (Test-Path "$STD\server.js")) { Write-Host "빌드 실패 — standalone/server.js 없음" -ForegroundColor Red; exit 1 }

Write-Host "[3/5] static/public → standalone 복사..." -ForegroundColor Cyan
if (Test-Path "$STD\.next\static") { Remove-Item "$STD\.next\static" -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$STD\.next" | Out-Null
Copy-Item "$WEB\.next\static" "$STD\.next\static" -Recurse -Force
if (Test-Path "$WEB\public") {
    if (Test-Path "$STD\public") { Remove-Item "$STD\public" -Recurse -Force }
    Copy-Item "$WEB\public" "$STD\public" -Recurse -Force
}

Write-Host "[4/5] standalone env 로컬 보정 (BACKEND_URL·API_PASS)..." -ForegroundColor Cyan
if (Test-Path "$WEB\.env.production.local") { Copy-Item "$WEB\.env.production.local" "$STD\.env.production.local" -Force }
$envFile = "$STD\.env.production"
if (Test-Path $envFile) {
    $out = @(); $seenPass = $false
    foreach ($ln in (Get-Content $envFile)) {
        if     ($ln -match "^BACKEND_URL=")     { $ln = "BACKEND_URL=http://localhost:8401" }
        elseif ($ln -match "^API_BASE_URL=")    { $ln = "API_BASE_URL=http://localhost:8401" }
        elseif ($ln -match "^FASTAPI_BASE_URL=") { $ln = "FASTAPI_BASE_URL=http://localhost:8401/api/v1" }
        elseif ($ln -match "^API_PASS=")        { $ln = "API_PASS=haehan2024!"; $seenPass = $true }
        $out += $ln
    }
    if (-not $seenPass) { $out += "API_PASS=haehan2024!" }
    Write-EnvNoBom $envFile $out
}

Write-Host "[5/5] Next 서버 재시작..." -ForegroundColor Cyan
$env:PORT = "3000"; $env:HOSTNAME = "0.0.0.0"; $env:OWNER_MODE = "true"
Start-Process -FilePath $node -ArgumentList "server.js" -WorkingDirectory $STD -WindowStyle Hidden `
    -RedirectStandardOutput "$ROOT\data\next_out.log" -RedirectStandardError "$ROOT\data\next_err.log"
$ok = $false
for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep -Seconds 1
    try { if ((Invoke-WebRequest "http://localhost:3000" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop).StatusCode -eq 200) { $ok = $true; break } } catch {}
}
if ($ok) { Write-Host "완료 — Next(3000) 200 OK. 프론트 변경 반영됨." -ForegroundColor Green }
else     { Write-Host "Next 미응답 — data/next_err.log 확인" -ForegroundColor Red }
