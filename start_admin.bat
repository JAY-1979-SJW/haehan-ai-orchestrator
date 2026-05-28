@echo off
setlocal
pushd "%~dp0\admin-web" >nul

echo [INFO] Admin Web 개발 서버 시작
echo [INFO] 포트: 3000 (or 3001)

npm run dev

popd >nul
