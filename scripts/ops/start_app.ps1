# 앱 전체 스택 시작 — 서버는 백그라운드, Electron 앱만 정면 표시
$ROOT = "C:\work\01. haehan-ai-orchestrator"

# CDP 캐시 정리 (쿠키·로그인 세션 보존, 캐시만 삭제)
& "$ROOT\scripts\ops\cleanup_cdp_cache.ps1"

# FastAPI (8401) — 미실행 시에만 시작
try { Invoke-RestMethod http://localhost:8401/api/v1/health -ErrorAction Stop | Out-Null }
catch {
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command", `
        "cd '$ROOT'; python -m uvicorn ai_orchestrator.server:app --host 0.0.0.0 --port 8401 --log-level warning"
    Start-Sleep 4
}

# Next.js (3000) — 미실행 시에만 시작
try { Invoke-WebRequest http://localhost:3000 -UseBasicParsing -ErrorAction Stop | Out-Null }
catch {
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command", `
        "cd '$ROOT\admin-web'; npm run dev"
}

# Electron 앱 실행
Start-Process "$ROOT\dist-installer\win-unpacked\Haehan AI.exe"
