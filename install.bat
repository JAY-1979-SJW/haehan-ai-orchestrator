@echo off
setlocal

pushd "%~dp0" >nul

if not exist "logs" mkdir "logs"
if not exist "config" mkdir "config"

if not exist "start.bat" (
  echo [ERROR] start.bat not found in this folder.
  popd >nul
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; " ^
  "try { " ^
  "$root=(Get-Location).Path; " ^
  "$desktopOverride=[Environment]::GetEnvironmentVariable('HAEHAN_PORTABLE_DESKTOP_DIR','Process'); " ^
  "if ([string]::IsNullOrWhiteSpace($desktopOverride)) { $desktop=[Environment]::GetFolderPath('Desktop') } else { $desktop=$desktopOverride; New-Item -ItemType Directory -Path $desktop -Force | Out-Null }; " ^
  "$shortcutName=[Environment]::GetEnvironmentVariable('HAEHAN_PORTABLE_SHORTCUT_NAME','Process'); " ^
  "if ([string]::IsNullOrWhiteSpace($shortcutName)) { $shortcutName='HaehanAI Desktop' }; " ^
  "if (-not $shortcutName.EndsWith('.lnk',[StringComparison]::OrdinalIgnoreCase)) { $shortcutName += '.lnk' }; " ^
  "$lnk=Join-Path $desktop $shortcutName; " ^
  "$shell=New-Object -ComObject WScript.Shell; " ^
  "$shortcut=$shell.CreateShortcut($lnk); " ^
  "$shortcut.TargetPath=Join-Path $root 'start.bat'; " ^
  "$shortcut.WorkingDirectory=$root; " ^
  "$shortcut.Description='HaehanAI Desktop portable launcher'; " ^
  "$exeCandidates=@((Join-Path $root 'HaehanAI-Desktop.exe'),(Join-Path $root 'HaehanAI-Desktop\HaehanAI-Desktop.exe'),(Join-Path $root 'dist\HaehanAI-Desktop\HaehanAI-Desktop.exe')); " ^
  "$exe=$exeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1; " ^
  "if ($exe) { $shortcut.IconLocation=$exe }; " ^
  "$shortcut.Save(); " ^
  "if (-not (Test-Path -LiteralPath $lnk)) { throw ('Shortcut was not created: ' + $lnk) }; " ^
  "Write-Host ('Shortcut created: ' + $lnk); " ^
  "} catch { Write-Error $_; exit 1 }"

if errorlevel 1 (
  echo [ERROR] Failed to create desktop shortcut.
  echo Run diagnostics.bat and send the latest logs\diagnostics_*.txt file to support.
  popd >nul
  exit /b 1
)

echo [OK] Portable install complete.
echo [OK] logs and config folders are ready.
echo [OK] Use the desktop shortcut or start.bat to run HaehanAI Desktop.

popd >nul
exit /b 0
