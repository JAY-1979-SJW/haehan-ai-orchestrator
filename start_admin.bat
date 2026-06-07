@echo off
setlocal
pushd "%~dp0\admin-web" >nul

echo [INFO] Admin Web 개발 서버 시작 확인 중...

:: 포트 3000 이미 사용 중이면 스킵
netstat -ano | findstr ":3000 " >nul 2>&1
if not errorlevel 1 (
    echo [INFO] 포트 3000 이미 실행 중 - 별도 시작 불필요
    popd >nul
    exit /b 0
)

echo [INFO] Next.js 개발 서버 시작 (백그라운드)...

:: npm run dev 를 백그라운드로 실행 (로그는 ..\data\next_out.log)
if not exist "..\data" mkdir "..\data"
start /min "NextJS-Dev" cmd /c "npm run dev > ..\data\next_out.log 2>&1"

echo [INFO] 시작됨. 로그: data\next_out.log

popd >nul
