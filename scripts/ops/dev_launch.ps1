# dev_launch.ps1 — 개발 모드 런처
# Claude Code 코드 수정 → 앱 실시간 반영
#
# 반영 속도:
#   Python (ai_orchestrator/**) → uvicorn --reload → 1~2초
#   Next.js (admin-web/src/**)  → Turbopack HMR   → <1초 (webview 자동 갱신)
#   Electron (main.js/lib/**)   → Electron 재시작 필요 (스크립트 재실행)

param(
    [switch]$NoElectron,  # Next.js + FastAPI만 (Electron 제외)
    [switch]$Restart      # 기존 프로세스 종료 후 재시작
)

$ROOT = "C:\work\01. haehan-ai-orchestrator"
$ADMINWEB = "$ROOT\admin-web"

Write-Host "=== Haehan AI 개발 모드 런처 ===" -ForegroundColor Cyan

# ── 1. 기존 프로세스 정리 ──────────────────────────────────────────────────
if ($Restart) {
    Write-Host "[1/4] 기존 프로세스 정리..." -ForegroundColor Yellow

    # FastAPI 종료
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -like "*uvicorn*ai_orchestrator*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }

    # Next.js dev 종료
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -like "*next*dev*" -or $_.CommandLine -like "*start-server*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }

    # Electron 앱 종료
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -like "*dist-installer*Haehan AI*" -or $_.CommandLine -like "*electron*admin-web*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }

    Start-Sleep -Seconds 2
    Write-Host "   기존 프로세스 정리 완료" -ForegroundColor Green
}

# ── 2. FastAPI (--reload) ──────────────────────────────────────────────────
Write-Host "[2/4] FastAPI 시작 (--reload, port 8401)..." -ForegroundColor Yellow

# 이미 실행 중인지 확인
$fastapiRunning = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*uvicorn*ai_orchestrator*" -and $_.CommandLine -like "*8401*" }

if ($fastapiRunning -and -not $Restart) {
    $reloadMode = $fastapiRunning.CommandLine -like "*--reload*"
    if ($reloadMode) {
        Write-Host "   FastAPI 이미 --reload 모드로 실행 중 (PID=$($fastapiRunning.ProcessId))" -ForegroundColor Green
    } else {
        Write-Host "   FastAPI 재시작 (--reload 없음 → 추가)..." -ForegroundColor Yellow
        Stop-Process -Id $fastapiRunning.ProcessId -Force -EA SilentlyContinue
        Start-Sleep -Seconds 1
        Start-Process "python" `
            "-m uvicorn ai_orchestrator.server:app --host 127.0.0.1 --port 8401 --reload --reload-dir ai_orchestrator --reload-dir scripts" `
            -WorkingDirectory $ROOT -WindowStyle Hidden
        Write-Host "   FastAPI --reload 재시작 완료" -ForegroundColor Green
    }
} else {
    Start-Process "python" `
        "-m uvicorn ai_orchestrator.server:app --host 127.0.0.1 --port 8401 --reload --reload-dir ai_orchestrator --reload-dir scripts" `
        -WorkingDirectory $ROOT -WindowStyle Hidden
    Write-Host "   FastAPI --reload 시작 완료" -ForegroundColor Green
}

# ── 3. Next.js dev (Turbopack HMR) ────────────────────────────────────────
Write-Host "[3/4] Next.js dev 서버 시작 (Turbopack HMR)..." -ForegroundColor Yellow

$nextRunning = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*next*" -and $_.CommandLine -like "*3000*" }

if (-not $nextRunning) {
    # .env.local 확인 (AUTH_ENABLED=false for dev)
    $envLocal = "$ADMINWEB\.env.local"
    if (Test-Path $envLocal) {
        $content = Get-Content $envLocal -Raw
        if ($content -notmatch "AUTH_ENABLED") {
            Add-Content $envLocal "`nAUTH_ENABLED=false"
        }
    }
    Start-Process "cmd" "/c cd /d `"$ADMINWEB`" && npx next dev --turbo -p 3000 2>&1" `
        -WindowStyle Hidden
    Write-Host "   Next.js dev 시작 중..." -ForegroundColor Yellow

    # 포트 3000 준비 대기 (최대 30초)
    $deadline = (Get-Date).AddSeconds(30)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $null = [System.Net.WebClient]::new().DownloadString("http://127.0.0.1:3000")
            $ready = $true; break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if ($ready) { Write-Host "   Next.js dev 준비 완료 ✓" -ForegroundColor Green }
    else { Write-Host "   ⚠️ Next.js dev 30초 타임아웃 — 수동 확인 필요" -ForegroundColor Red }
} else {
    Write-Host "   Next.js 이미 실행 중 (port 3000)" -ForegroundColor Green
}

# ── 4. Electron 앱 실행 ──────────────────────────────────────────────────
if (-not $NoElectron) {
    Write-Host "[4/4] Electron 앱 시작..." -ForegroundColor Yellow

    $electronRunning = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like "*Haehan*" }

    if ($electronRunning) {
        Write-Host "   Electron 앱 이미 실행 중 (PID=$($electronRunning.Id))" -ForegroundColor Green
        Write-Host "   ℹ️  main.js 변경 시 이 스크립트를 -Restart 옵션으로 재실행하세요" -ForegroundColor DarkGray
    } else {
        # dist-installer Electron (dev Next.js 자동 감지)
        $electronExe = "$ROOT\dist-installer\win-unpacked\Haehan AI.exe"
        if (Test-Path $electronExe) {
            Start-Process $electronExe
            Write-Host "   Electron 앱 시작 완료" -ForegroundColor Green
        } else {
            # 소스에서 직접 실행 (npx electron)
            Write-Host "   dist-installer 없음 → npx electron으로 직접 실행" -ForegroundColor Yellow
            Start-Process "cmd" "/c cd /d `"$ADMINWEB`" && npx electron . 2>&1" -WindowStyle Normal
        }
    }
}

Write-Host ""
Write-Host "=== 개발 모드 실행 중 ===" -ForegroundColor Cyan
Write-Host "  FastAPI  : http://127.0.0.1:8401  (Python 저장 → 1~2초 자동 반영)"
Write-Host "  Next.js  : http://127.0.0.1:3000  (TSX 저장 → <1초 HMR 자동 반영)"
Write-Host "  재시작   : .\scripts\ops\dev_launch.ps1 -Restart"
Write-Host "  서버만   : .\scripts\ops\dev_launch.ps1 -NoElectron"
