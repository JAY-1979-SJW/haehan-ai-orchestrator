@echo off
setlocal
pushd "%~dp0" >nul

echo [INFO] haehan-ai-orchestrator API 서버 시작
echo [INFO] 포트: 8400 / 호스트: 127.0.0.1

if not exist ".env" (
    echo [WARN] .env 파일 없음 - .env.example 복사 필요
)

if not exist "logs" mkdir "logs"

python -m uvicorn ai_orchestrator.asgi:app ^
    --host 127.0.0.1 ^
    --port 8400 ^
    --reload ^
    --log-level info

popd >nul
