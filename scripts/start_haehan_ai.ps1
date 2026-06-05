# Haehan AI 전체 스택 시작 스크립트
# 순서: 1. FastAPI(소스 uvicorn) → 2. Next.js standalone → 3. CDP Chrome → 4. Electron 앱
# Windows 시작프로그램 등록 시 자동 실행

# ── 콘솔 숨김 (앱 실행 터미널 백그라운드) ──────────────────────────────────────
# launcher PowerShell 창을 즉시 숨겨 백그라운드로. 진행 로그는 data/server_*.log 참고.
try {
    Add-Type -Name Win32 -Namespace Hide -MemberDefinition '[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int n); [DllImport("kernel32.dll")] public static extern System.IntPtr GetConsoleWindow();' -ErrorAction SilentlyContinue
    $consoleH = [Hide.Win32]::GetConsoleWindow()
    if ($consoleH -ne [System.IntPtr]::Zero) { [Hide.Win32]::ShowWindow($consoleH, 0) | Out-Null }  # 0 = SW_HIDE
} catch {}

$ROOT     = "C:\work\01. haehan-ai-orchestrator"
$ELECTRON = "$ROOT\dist-installer\win-unpacked\Haehan AI.exe"
$FASTAPI  = "$ROOT\dist-installer\win-unpacked\resources\server\haehan-server\haehan-server.exe"
$NEXTJS   = "$ROOT\admin-web\.next\standalone\server.js"

function Test-Port($port) {
    try {
        $r = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$port")
        $r.Timeout = 2000
        $r.GetResponse().Close()
        return $true
    } catch { return $false }
}

function Wait-Port($port, $label, $maxSec = 30) {
    for ($i = 0; $i -lt $maxSec; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Port $port) { Write-Host "[$label] 준비 완료 (포트 $port)"; return $true }
    }
    Write-Host "[$label] 시작 타임아웃 ${maxSec}초 — 포트 $port 응답 없음" -ForegroundColor Red
    return $false
}

# ── 1. FastAPI 소스 서버 (포트 8401) ─────────────────────────────────────────
# frozen exe(haehan-server.exe)는 옛 코드를 박제 → 소스 변경 미반영. 소스(uvicorn)를
# pythonw(콘솔 없음)로 띄워 코드 수정이 재시작만으로 즉시 반영되게 한다. 로그는 파일로.
$PYW = "C:\Users\skyjw\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
if (-not (Test-Path $PYW)) { $PYW = (Get-Command pythonw -ErrorAction SilentlyContinue).Source }
if (-not $PYW) { $PYW = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (Test-Port 8401) {
    Write-Host "[1/4] FastAPI 이미 실행 중"
} else {
    Write-Host "[1/4] FastAPI 소스 서버 시작..."
    if (-not $PYW -or -not (Test-Path $PYW)) {
        Write-Host "[1/4] python 실행파일 없음: $PYW" -ForegroundColor Red; exit 1
    }
    $env:HAEHAN_DATA_DIR = "$ROOT\data"
    Start-Process -FilePath $PYW `
        -ArgumentList "-m","uvicorn","ai_orchestrator.server:app","--host","127.0.0.1","--port","8401" `
        -WorkingDirectory $ROOT `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$ROOT\data\server_out.log" `
        -RedirectStandardError  "$ROOT\data\server_err.log"
    if (-not (Wait-Port 8401 "FastAPI" 40)) { exit 1 }
}

# ── 2. Next.js standalone 서버 (포트 3000) ───────────────────────────────────
if (Test-Port 3000) {
    Write-Host "[2/4] Next.js 이미 실행 중"
} else {
    Write-Host "[2/4] Next.js 서버 시작..."
    if (-not (Test-Path $NEXTJS)) {
        Write-Host "[2/4] Next.js standalone 없음: $NEXTJS" -ForegroundColor Red; exit 1
    }
    $env:PORT      = "3000"
    $env:HOSTNAME  = "0.0.0.0"
    $env:NODE_ENV  = "production"
    $env:OWNER_MODE = "true"
    Start-Process node -ArgumentList $NEXTJS `
        -WorkingDirectory (Split-Path $NEXTJS) `
        -WindowStyle Hidden
    if (-not (Wait-Port 3000 "Next.js" 30)) { exit 1 }
}

# ── 3. CDP Chrome (포트 9222) ─────────────────────────────────────────────────
$cdpAlive = $false
try {
    $r = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:9222/json")
    $r.Timeout = 2000; $r.GetResponse().Close(); $cdpAlive = $true
} catch {}

if ($cdpAlive) {
    Write-Host "[3/4] CDP Chrome 이미 실행 중"
} else {
    Write-Host "[3/4] CDP Chrome 시작..."
    # 번들 Chromium 우선, 없으면 시스템 Chrome
    $chromePaths = @(
        "$ROOT\dist-installer\win-unpacked\resources\server\haehan-server\_internal\chromium\chrome-win64\chrome.exe",
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $chromeExe = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($chromeExe) {
        $profileDir = "$ROOT\data\cdp_profile\ai_chrome"
        Start-Process $chromeExe -ArgumentList `
            "--remote-debugging-port=9222",
            "--user-data-dir=`"$profileDir`"",
            "--no-first-run", "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--window-position=9999,9999" `
            -WindowStyle Minimized
        # CDP는 빠르게 뜨므로 5초만 대기
        Start-Sleep -Seconds 5
        try {
            $r = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:9222/json")
            $r.Timeout = 2000; $r.GetResponse().Close()
            Write-Host "[3/4] CDP Chrome 준비 완료 (포트 9222)"
        } catch { Write-Host "[3/4] CDP Chrome 포트 9222 응답 없음 — 계속 진행" -ForegroundColor Yellow }
    } else {
        Write-Host "[3/4] Chrome 실행 파일 없음 — CDP 스킵" -ForegroundColor Yellow
    }
}

# ── 4. Electron 앱 ──────────────────────────────────────────────────────────
$already = Get-Process | Where-Object { $_.Path -eq $ELECTRON } | Select-Object -First 1
if ($already) {
    Write-Host "[4/4] Haehan AI 이미 실행 중 (PID $($already.Id))"
} else {
    Write-Host "[4/4] Haehan AI 시작..."
    if (-not (Test-Path $ELECTRON)) {
        Write-Host "[4/4] Haehan AI.exe 없음: $ELECTRON" -ForegroundColor Red; exit 1
    }
    Start-Process $ELECTRON
    Write-Host "[4/4] Haehan AI 시작됨"
}

Write-Host "`n모든 서비스 시작 완료" -ForegroundColor Green
