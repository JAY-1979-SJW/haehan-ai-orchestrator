@echo off
setlocal

pushd "%~dp0" >nul

if not exist "logs" mkdir "logs"
if not exist "config" mkdir "config"

for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%I"
set "REPORT=logs\diagnostics_%TS%.txt"

> "%REPORT%" echo HAEHAN_DESKTOP_PORTABLE_DIAGNOSTICS
>> "%REPORT%" echo generated_at=%DATE% %TIME%
>> "%REPORT%" echo app_root=%CD%
>> "%REPORT%" echo.

>> "%REPORT%" echo [files]
if exist "install.bat" (>> "%REPORT%" echo install_bat=present) else (>> "%REPORT%" echo install_bat=missing)
if exist "start.bat" (>> "%REPORT%" echo start_bat=present) else (>> "%REPORT%" echo start_bat=missing)
if exist "diagnostics.bat" (>> "%REPORT%" echo diagnostics_bat=present) else (>> "%REPORT%" echo diagnostics_bat=missing)
if exist "uninstall.bat" (>> "%REPORT%" echo uninstall_bat=present) else (>> "%REPORT%" echo uninstall_bat=missing)
dir /b "README_*.txt" >nul 2>nul
if errorlevel 1 (>> "%REPORT%" echo readme=missing) else (>> "%REPORT%" echo readme=present)

set "APP_EXE="
if exist "HaehanAI-Desktop.exe" set "APP_EXE=%CD%\HaehanAI-Desktop.exe"
if not defined APP_EXE if exist "HaehanAI-Desktop\HaehanAI-Desktop.exe" set "APP_EXE=%CD%\HaehanAI-Desktop\HaehanAI-Desktop.exe"
if not defined APP_EXE if exist "dist\HaehanAI-Desktop\HaehanAI-Desktop.exe" set "APP_EXE=%CD%\dist\HaehanAI-Desktop\HaehanAI-Desktop.exe"

if defined APP_EXE (
  >> "%REPORT%" echo desktop_exe=present
  >> "%REPORT%" echo desktop_exe_path=%APP_EXE%
) else (
  >> "%REPORT%" echo desktop_exe=missing
)

if exist "_internal" (>> "%REPORT%" echo internal_folder=present) else (>> "%REPORT%" echo internal_folder=not_found_at_root)
if exist "HaehanAI-Desktop\_internal" (>> "%REPORT%" echo internal_folder_nested=present) else (>> "%REPORT%" echo internal_folder_nested=not_found)
if exist "dist\HaehanAI-Desktop\_internal" (>> "%REPORT%" echo internal_folder_dist=present) else (>> "%REPORT%" echo internal_folder_dist=not_found)

>> "%REPORT%" echo.
>> "%REPORT%" echo [folders]
if exist "logs" (>> "%REPORT%" echo logs=present) else (>> "%REPORT%" echo logs=missing)
if exist "config" (>> "%REPORT%" echo config=present) else (>> "%REPORT%" echo config=missing)

>> "%REPORT%" echo.
>> "%REPORT%" echo [port]
for /f "delims=" %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue; if ($p) { 'port_8765=in_use' } else { 'port_8765=free' }"') do >> "%REPORT%" echo %%P

>> "%REPORT%" echo.
>> "%REPORT%" echo [environment]
>> "%REPORT%" echo secret_values_printed=false
for /f "delims=" %%E in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$names=@('HAEHAN_DESKTOP_OPS_BASIC_USER','HAEHAN_DESKTOP_OPS_BASIC_PASSWORD','OPENAI_API_KEY','ANTHROPIC_API_KEY'); foreach ($n in $names) { $present=[bool][Environment]::GetEnvironmentVariable($n); '{0}_present={1}' -f $n,$present }"') do >> "%REPORT%" echo %%E

echo [OK] Diagnostics saved to %REPORT%
echo Secret values were not printed.

popd >nul
exit /b 0
