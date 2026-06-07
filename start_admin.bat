@echo off
setlocal

:: Next.js(admin-web) dev 서버를 로그 저장하며 안전하게 실행.
:: 실제 로직은 PowerShell 런처에 위임 — Start-Process -RedirectStandardOutput 로
:: 로그 경로를 값 전달해 공백("01. ") 경로에서도 리다이렉트 깨짐이 없다.
:: (과거: npm run dev > ...01. haehan...\nextjs.log 가 공백에서 잘려 인자로 넘어가던 버그)

echo [INFO] Admin Web 개발 서버 시작...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ops\start_admin_logged.ps1"

endlocal
