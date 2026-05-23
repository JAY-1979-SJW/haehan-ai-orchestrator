@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; " ^
  "$desktopOverride=[Environment]::GetEnvironmentVariable('HAEHAN_PORTABLE_DESKTOP_DIR','Process'); " ^
  "if ([string]::IsNullOrWhiteSpace($desktopOverride)) { $desktop=[Environment]::GetFolderPath('Desktop') } else { $desktop=$desktopOverride }; " ^
  "$shortcutName=[Environment]::GetEnvironmentVariable('HAEHAN_PORTABLE_SHORTCUT_NAME','Process'); " ^
  "if ([string]::IsNullOrWhiteSpace($shortcutName)) { $shortcutName='HaehanAI Desktop' }; " ^
  "if (-not $shortcutName.EndsWith('.lnk',[StringComparison]::OrdinalIgnoreCase)) { $shortcutName += '.lnk' }; " ^
  "$lnk=Join-Path $desktop $shortcutName; " ^
  "try { if (Test-Path $lnk) { try { Remove-Item -LiteralPath $lnk -Force -ErrorAction Stop } catch { & attrib -R -S -H $lnk 2>$null; Start-Sleep -Milliseconds 300; [System.GC]::Collect(); [System.GC]::WaitForPendingFinalizers(); [System.IO.File]::Delete($lnk) }; if (Test-Path -LiteralPath $lnk) { throw ('Shortcut still exists: ' + $lnk) }; Write-Host ('Shortcut removed: ' + $lnk) } else { Write-Host 'Shortcut not found.' } } catch { Write-Error $_; exit 1 }"

if errorlevel 1 (
  echo [ERROR] Failed to remove desktop shortcut.
  exit /b 1
)

echo [OK] Uninstall complete. App files, logs, and config were not deleted.
exit /b 0
