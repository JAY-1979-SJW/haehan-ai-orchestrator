# Next.js(admin-web) dev 서버를 "로그 저장하며" 안전하게 실행하는 런처.
#
# 왜 이 스크립트인가:
#   `npm run dev > C:\work\01. haehan-ai-orchestrator\nextjs.log` 처럼 쉘 리다이렉트(>)로
#   로그를 저장하면, 경로의 공백("01. ")에서 토큰이 잘려 뒷부분이 next dev 의 인자로 넘어가
#   "Invalid project directory" 에러가 난다. 여기서는 Start-Process 의 -RedirectStandardOutput
#   파라미터로 파일 경로를 "값"으로 전달 → 쉘 파싱을 거치지 않아 공백이 있어도 100% 안전.
#
# 사용:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\ops\start_admin_logged.ps1"
#   실시간 로그 보기:  Get-Content "C:\work\01. haehan-ai-orchestrator\data\nextjs_dev.out.log" -Wait

$ErrorActionPreference = "Stop"
$ROOT    = "C:\work\01. haehan-ai-orchestrator"
$WEBDIR  = "$ROOT\admin-web"
$NEXTBIN = "$WEBDIR\node_modules\next\dist\bin\next"
$LOGDIR  = "$ROOT\data"
$OUT     = "$LOGDIR\nextjs_dev.out.log"   # 표준 출력 로그
$ERRLOG  = "$LOGDIR\nextjs_dev.err.log"   # 표준 에러 로그(별도 파일 필수)

# ── 이미 3000 떠 있으면 중복 실행 방지 ──────────────────────────────────────
$alive = $false
try {
    $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:3000")
    $req.Timeout = 2000
    $req.GetResponse().Close()
    $alive = $true
} catch { }
if ($alive) {
    Write-Host "[admin-logged] 포트 3000 이미 실행 중 — 중복 시작 생략"
    return
}

if (-not (Test-Path $NEXTBIN)) {
    Write-Host "[admin-logged] next 실행파일 없음: $NEXTBIN" -ForegroundColor Red
    exit 1
}
New-Item -ItemType Directory -Force -Path $LOGDIR | Out-Null

$env:NODE_ENV   = "development"
$env:OWNER_MODE = "true"

# -RedirectStandardOutput/Error 로 경로를 값 전달 → 공백 안전. -WindowStyle Hidden 으로 콘솔창 없음.
$proc = Start-Process node `
    -ArgumentList "`"$NEXTBIN`"", "dev", "-p", "3000" `
    -WorkingDirectory $WEBDIR `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OUT `
    -RedirectStandardError  $ERRLOG `
    -PassThru

Write-Host "[admin-logged] Next.js dev 시작 (PID=$($proc.Id))"
Write-Host "[admin-logged] 출력 로그: $OUT"
Write-Host "[admin-logged] 에러 로그: $ERRLOG"
Write-Host "[admin-logged] 실시간 보기: Get-Content `"$OUT`" -Wait"
