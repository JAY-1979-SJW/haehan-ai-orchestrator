@echo off
setlocal

pushd "%~dp0" >nul

if not exist "logs" mkdir "logs"
if not exist "config" mkdir "config"

set "APP_EXE="
if exist "HaehanAI-Desktop.exe" set "APP_EXE=%CD%\HaehanAI-Desktop.exe"
if not defined APP_EXE if exist "HaehanAI-Desktop\HaehanAI-Desktop.exe" set "APP_EXE=%CD%\HaehanAI-Desktop\HaehanAI-Desktop.exe"
if not defined APP_EXE if exist "dist\HaehanAI-Desktop\HaehanAI-Desktop.exe" set "APP_EXE=%CD%\dist\HaehanAI-Desktop\HaehanAI-Desktop.exe"

if not defined APP_EXE (
  echo [ERROR] HaehanAI-Desktop.exe was not found.
  echo Run diagnostics.bat and check the latest logs\diagnostics_*.txt file.
  popd >nul
  exit /b 1
)

echo [INFO] Starting HaehanAI Desktop...
start "" "%APP_EXE%"
if errorlevel 1 (
  echo [ERROR] Failed to start HaehanAI Desktop.
  echo Run diagnostics.bat and check the latest logs\diagnostics_*.txt file.
  popd >nul
  exit /b 1
)

popd >nul
exit /b 0
